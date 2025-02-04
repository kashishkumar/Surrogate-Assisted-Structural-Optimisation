import numpy as np

def meshtruss(p1,p2,nx,ny):
  nodes = []
  bars = []
  xx = np.linspace(p1[0],p2[0],nx+1)
  yy = np.linspace(p1[1],p2[1],ny+1)
  for y in yy:
    for x in xx:
      nodes.append([x,y])
  for j in range(ny):
      for i in range(nx):
        n1 = i + j*(nx+1)
        n2 = n1 + 1
        n3 = n1 + nx + 1
        n4 = n3 + 1
        bars.extend([[n1,n2],[n1,n3],[n1,n4],[n2,n3]])
      bars.append([n2,n4])
  index = ny*(nx+1) + 1
  for j in range(nx):
    bars.append([index+j-1,index+j])
  return np.array(nodes), np.array(bars)

#!pip install openopt
#!pip install FuncDesigner
#!pip install nlopt
#!pip install pyDOE

from openopt import NLP
from matplotlib.pyplot import figure,show


import pyDOE
from pyDOE import *
from scipy.stats.distributions import norm

#help(NLP)

from profilestats import profile

import tensorflow as tf
from tensorflow import keras
import sklearn

def Surrogate(coord,connec,E,F,freenode,samples=100,testratio=0.2):
    # Defining Member Properties
    n = connec.shape[0]  # Number of members
    m = coord.shape[0]   # Number of nodes
    vectors = coord[connec[:,1],:] - coord[connec[:,0],:]  # Nonnormalised direction cosines
    l = np.sqrt((vectors**2).sum(axis=1)) # Length
    e = vectors.T/l # Normalised Direction Cosines
    B = (e[np.newaxis] * e[:,np.newaxis]).T # Transformation Matrix

    # Defining Structure Stiffness Matrix
    def K(x):
        D = E * x/l
        kx = e * D
        K = np.zeros((2*m, 2*m))
        for i in range(n): # Local Stiffness Matrices
          aux = 2*connec[i,:]
          index = np.r_[aux[0]:aux[0]+2, aux[1]:aux[1]+2]
          k0 = np.concatenate((np.concatenate((B[i],-B[i]),axis=1), \
          np.concatenate((-B[i],B[i]),axis=1)), axis=0)
          K[np.ix_(index,index)] = K[np.ix_(index,index)] + D[i] * k0
        block = freenode.flatten().nonzero()[0]
        matrix = K[np.ix_(block,block)]
        return matrix


    block = freenode.flatten().nonzero()[0]
    rhs = F.flatten()[block]

    nsurr=n # Design Variables
    m_train=int((1-testratio)*samples)
    x=np.random.random(n)
    dof= rhs.shape[0] # Degree of freedom

    #Generating training inputs
    X = lhs(nsurr, samples=m_train) # Latin Hypercube sampling with uniform Distribution
    #X = norm(loc=0, scale=1).ppf(X)  # Normal Distribution

    #means = [1, 2, 3, 4]
    #stdvs = [0.1, 0.5, 1, 0.25]
    #for i in xrange(4):
      #X[:, i] = norm(loc=means[i], scale=stdvs[i]).ppf(X[:, i])#

    #Generating training outputs

    U=np.ones((len(X),dof))
    for i in range(len(X)):
      U[i]=np.linalg.solve(K(X[i]),rhs)

    # Generating Test input and output
    m_test=int(testratio*samples)
    X_test = lhs(n, samples=m_test)
    U_test=np.ones((len(X_test),dof))
    for i in range(len(X_test)):
      U_test[i]=np.linalg.solve(K(X_test[i]),rhs)

    # Defining the Model
    model_ANN =tf.keras.Sequential()
    model_ANN.add(keras.layers.Dense(8,activation='relu',input_shape=(n,)))
    model_ANN.add(keras.layers.Dense(dof))

    # Define Model Training Parameters
    model_ANN.compile(optimizer='adam',loss='MSE',metrics=['mae'])

    # Training the model
    model_ANN.fit(X,U,epochs=100,validation_split=0.15)

    # Testing the Model
    model_ANN.evaluate(X_test,U_test)

    # Predicting
    return model_ANN

@profile(print_stats=10, dump_stats=True)
def opttruss(coord,connec,E,F,freenode,V0,plotdisp=False,solver="ralg"):
  n = connec.shape[0]  # Number of members
  m = coord.shape[0]   # Number of nodes
  vectors = coord[connec[:,1],:] - coord[connec[:,0],:]  # Nonnormalised direction cosines
  l = np.sqrt((vectors**2).sum(axis=1)) #Length
  e = vectors.T/l #Normalised Direction Cosines
  B = (e[np.newaxis] * e[:,np.newaxis]).T # Transformation Matrix

  def fobj(x):
      D = E * x/l
      kx = e * D
      K = np.zeros((2*m, 2*m))
      for i in range(n): # Local Stiffness Matrices 
        aux = 2*connec[i,:]
        index = np.r_[aux[0]:aux[0]+2, aux[1]:aux[1]+2]
        k0 = np.concatenate((np.concatenate((B[i],-B[i]),axis=1), \
        np.concatenate((-B[i],B[i]),axis=1)), axis=0)
        K[np.ix_(index,index)] = K[np.ix_(index,index)] + D[i] * k0
      block = freenode.flatten().nonzero()[0]
      matrix = K[np.ix_(block,block)] # Global Stiffness Matrix
      rhs = F.flatten()[block]        # Force Vector
      solution = np.linalg.solve(matrix,rhs) # Solving Ax=B to get U
      u=freenode.astype(float).flatten()
      u[block] = solution
      U = u.reshape(m,2)
      axial = ((U[connec[:,1],:] - U[connec[:,0],:]) * kx.T).sum(axis=1) # Axial Load Calculation
      stress = axial / x # Axial Stress
      cost = (U * F).sum() # Compliance Matrix as cost function
      dcost = -stress**2 / E * l # Derivative of cost function
      return cost, dcost, U, stress

  def volume(x):
      return (x * l).sum(), l

  def drawtruss(x,factor=3, wdt=5e2):
      U, stress = fobj(x)[2:]
      newcoor = coord + factor*U
      if plotdisp:
        fig = figure(figsize=(12,6))
        ax = fig.add_subplot(121)
        bx = fig.add_subplot(122)
      else:
        fig = figure()
        ax = fig.add_subplot(111)
      for i in range(n):
        bar1 = np.concatenate( (coord[connec[i,0],:][np.newaxis],
        coord[connec[i,1],:][np.newaxis]),axis=0 )
        bar2 = np.concatenate( (newcoor[connec[i,0],:][np.newaxis],
        newcoor[connec[i,1],:][np.newaxis]),axis=0 )
        if stress[i] > 0:
          clr = "r"
        else:
          clr = "b"
        ax.plot(bar1[:,0],bar1[:,1], color = clr, linewidth = wdt * x
        [i])
        ax.axis("equal")
        ax.set_title("Stress")
        if plotdisp:
          bx.plot(bar1[:,0],bar1[:,1], "r:")
          bx.plot(bar2[:,0],bar2[:,1], color = "k", linewidth= wdt
          * x[i])
          bx.axis("equal")
          bx.set_title("Displacement")
      show()

  # Parameters and Tolerances
  xmin = 1e-6 * np.ones(n)
  xmax = 1e-2 * np.ones(n)
  f = lambda x: fobj(x)[0]
  derf = lambda x: fobj(x)[1]
  totalvolume = volume(xmax)[0]
  constr = lambda x: 1./totalvolume * volume(x)[0] - V0
  dconstr= lambda x: 1./totalvolume * volume(x)[1]
  x0 = 1e-4*np.ones(n)
  problem = NLP(f,x0,df=derf,c=constr,dc=dconstr, lb=xmin, ub=xmax, name="Truss", iprint=100)
  result = problem.solve(solver)

  drawtruss(result.xf)
  pass

def remove_bar (connec ,n1 ,n2):
    bars = connec.tolist()
    for bar in bars[:]:
        if (bar[0] == n1 and bar[1] == n2) or (bar[0] == n2 and bar[1] == n1):
            bars.remove(bar)
            return np.array(bars)
        else:
            print ("There is no such bar")
            return connec

def remove_node(connec, n1):
    bars = connec.tolist()
    for bar in bars[:]:
        if bar[0] == n1 or bar[1] == n1:
            bars.remove(bar)
            return np.array(bars)

@profile(print_stats=10, dump_stats=True)
def opttruss_surr(coord,connec,E,F,freenode,V0,plotdisp=False,solver="ralg",samples=100,testratio=0.2):
  n = connec.shape[0]  # Number of members
  m = coord.shape[0]   # Number of nodes
  vectors = coord[connec[:,1],:] - coord[connec[:,0],:]  # Nonnormalised direction cosines
  l = np.sqrt((vectors**2).sum(axis=1)) #Length
  e = vectors.T/l #Normalised Direction Cosines
  B = (e[np.newaxis] * e[:,np.newaxis]).T # Transformation Matrix
  model=Surrogate(coord,connec,E,F,freenode,samples=samples,testratio=testratio)

  def fobj(x):
      D = E * x/l
      kx = e * D
      K = np.zeros((2*m, 2*m))
      for i in range(n): # Local Stiffness Matrices
        aux = 2*connec[i,:]
        index = np.r_[aux[0]:aux[0]+2, aux[1]:aux[1]+2]
        k0 = np.concatenate((np.concatenate((B[i],-B[i]),axis=1), \
        np.concatenate((-B[i],B[i]),axis=1)), axis=0)
        K[np.ix_(index,index)] = K[np.ix_(index,index)] + D[i] * k0
      block = freenode.flatten().nonzero()[0]
      matrix = K[np.ix_(block,block)] # Global Stiffness Matrix
      rhs = F.flatten()[block]        # Force Vector
      #solution = np.linalg.solve(matrix,rhs) # Solving Ax=B to get U
      solution=model.predict(x.reshape(1,n))  # Solving using Surrogate
      u=freenode.astype(float).flatten()
      u[block] = solution
      U = u.reshape(m,2)
      axial = ((U[connec[:,1],:] - U[connec[:,0],:]) * kx.T).sum(axis=1) # Axial Load Calculation
      stress = axial / x # Axial Stress
      cost = (U * F).sum() # Compliance Matrix as cost function
      dcost = -stress**2 / E * l # Derivative of cost function
      return cost, dcost, U, stress

  def volume(x):
      return (x * l).sum(), l

  def drawtruss(x,factor=3, wdt=5e2):
      U, stress = fobj(x)[2:]
      newcoor = coord + factor*U
      if plotdisp:
        fig = figure(figsize=(12,6))
        ax = fig.add_subplot(121)
        bx = fig.add_subplot(122)
      else:
        fig = figure()
        ax = fig.add_subplot(111)
      for i in range(n):
        bar1 = np.concatenate( (coord[connec[i,0],:][np.newaxis],
        coord[connec[i,1],:][np.newaxis]),axis=0 )
        bar2 = np.concatenate( (newcoor[connec[i,0],:][np.newaxis],
        newcoor[connec[i,1],:][np.newaxis]),axis=0 )
        if stress[i] > 0:
          clr = "r"
        else:
          clr = "b"
        ax.plot(bar1[:,0],bar1[:,1], color = clr, linewidth = wdt * x
        [i])
        ax.axis("equal")
        ax.set_title("Stress")
        if plotdisp:
          bx.plot(bar1[:,0],bar1[:,1], "r:")
          bx.plot(bar2[:,0],bar2[:,1], color = "k", linewidth= wdt
          * x[i])
          bx.axis("equal")
          bx.set_title("Displacement")
      show()

  # Parameters and Tolerances
  xmin = 1e-6 * np.ones(n)
  xmax = 1e-2 * np.ones(n)
  f = lambda x: fobj(x)[0]
  derf = lambda x: fobj(x)[1]
  totalvolume = volume(xmax)[0]
  constr = lambda x: 1./totalvolume * volume(x)[0] - V0
  dconstr= lambda x: 1./totalvolume * volume(x)[1]
  x0 = 1e-4*np.ones(n)
  problem = NLP(f,x0,df=derf,c=constr,dc=dconstr, lb=xmin, ub=xmax, name="Truss", iprint=100)
  result = problem.solve(solver)

  drawtruss(result.xf)
  pass

# Example 1
coord, connec = meshtruss((0,0), (0.6,0.4), 6, 4)
E0=1e+7
E = E0*np.ones(connec.shape[0])
coord.shape
loads = np.zeros_like(coord)
loads.shape
loads[20,1] = -100.
free = np.ones_like(coord).astype(int)
free[::7,:]=0
opttruss(coord,connec,E,loads,free,0.1,True,solver="scipy_slsqp")
Surrogate(coord,connec,E,loads,free,samples=100,testratio=0.2)
opttruss_surr(coord,connec,E,loads,free,0.1,True,solver="scipy_slsqp",samples=1000)

# Example 2
coord, connec = meshtruss((0,0),(0.6,0.4),6,4)
connec = remove_node(connec,16)
E0=1e+7
E = E0*np.ones(connec.shape[0])
loads = np.zeros_like(coord)
loads[20,1] = -100.
loads.flatten().shape
free = np.ones_like(coord).astype(int)
free[16,:]=0
free[::7,:]=0
opttruss(coord,connec,E,loads,free,0.1,solver="scipy_slsqp")
Surrogate(coord,connec,E,loads,free,samples=100,testratio=0.2)
opttruss_surr(coord,connec,E,loads,free,0.1,True,solver="scipy_slsqp",samples=1000)
