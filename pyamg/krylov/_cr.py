import warnings
from warnings import warn

import numpy as np
from scipy.sparse.linalg.isolve.utils import make_system
import scipy.sparse as sparse
from pyamg.util.linalg import norm

__all__ = ['cr']


def cr(A, b, x0=None, tol=1e-5, criteria='rr',
       maxiter=None, M=None,
       callback=None, residuals=None):
    """Conjugate Residual algorithm.

    Solves the linear system Ax = b. Left preconditioning is supported.
    The matrix A must be Hermitian symmetric (but not necessarily definite).

    Parameters
    ----------
    A : array, matrix, sparse matrix, LinearOperator
        n x n, linear system to solve
    b : array, matrix
        right hand side, shape is (n,) or (n,1)
    x0 : array, matrix
        initial guess, default is a vector of zeros
    tol : float
        Tolerance for stopping criteria
    criteria : string
        Stopping criteria, let r=r_k, x=x_k
        'rr':        ||r||       < tol ||b||
        'rr+':       ||r||       < tol (||b|| + ||A||_F ||x||)
        'MrMr':      ||M r||     < tol ||M b||
        if ||b||=0, then set ||b||=1 for these tests.
    maxiter : int
        maximum number of iterations allowed
    M : array, matrix, sparse matrix, LinearOperator
        n x n, inverted preconditioner, i.e. solve M A x = M b.
    callback : function
        User-supplied function is called after each iteration as
        callback(xk), where xk is the current solution vector
    residuals : list
        residual history in the 2-norm, including the initial residual

    Returns
    -------
    (xk, info)
    xk : an updated guess after k iterations to the solution of Ax = b
    info : halting status

            ==  =======================================
            0   successful exit
            >0  convergence to tolerance not achieved,
                return iteration count instead.
            <0  numerical breakdown, or illegal input
            ==  =======================================

    Notes
    -----
    The LinearOperator class is in scipy.sparse.linalg.interface.
    Use this class if you prefer to define A or M as a mat-vec routine
    as opposed to explicitly constructing the matrix.

    Examples
    --------
    >>> from pyamg.krylov.cr import cr
    >>> from pyamg.util.linalg import norm
    >>> import numpy as np
    >>> from pyamg.gallery import poisson
    >>> A = poisson((10,10))
    >>> b = np.ones((A.shape[0],))
    >>> (x,flag) = cr(A,b, maxiter=2, tol=1e-8)
    >>> print norm(b - A @ x)
    10.9370700187

    References
    ----------
    .. [1] Yousef Saad, "Iterative Methods for Sparse Linear Systems,
       Second Edition", SIAM, pp. 262-67, 2003
       http://www-users.cs.umn.edu/~saad/books.html

    """
    A, M, x, b, postprocess = make_system(A, M, x0, b)

    # Ensure that warnings are always reissued from this function
    warnings.filterwarnings('always', module='pyamg.krylov._cr')

    # determine maxiter
    if maxiter is None:
        maxiter = int(1.3*len(b)) + 2
    elif maxiter < 1:
        raise ValueError('Number of iterations must be positive')

    # setup method
    r = b - A @ x
    z = M @ r
    p = z.copy()
    zz = np.inner(z.conjugate(), z)

    normr = np.linalg.norm(r)

    if residuals is not None:
        residuals[:] = [normr]  # initial residual

    # Check initial guess if b != 0,
    normb = norm(b)
    if normb == 0.0:
        normb = 1.0  # reset so that tol is unscaled

    # set the stopping criteria (see the docstring)
    if criteria == 'rr':
        rtol = tol * normb
    elif criteria == 'rr+':
        if sparse.issparse(A.A):
            normA = norm(A.A.data)
        elif isinstance(A.A, np.ndarray):
            normA = norm(np.ravel(A.A))
        else:
            raise ValueError('Unable to use ||A||_F with the current matrix format.')
        rtol = tol * (normA * np.linalg.norm(x) + normb)
    elif criteria == 'MrMr':
        normr = np.sqrt(zz)
        normMb = norm(M @ b)
        rtol = tol * normMb
    else:
        raise ValueError('Invalid stopping criteria.')

    if normr < rtol:
        return (postprocess(x), 0)

    # How often should r be recomputed
    recompute_r = 8

    Az = A @ z
    rAz = np.inner(r.conjugate(), Az)
    Ap = A @ p

    it = 0

    while True:

        rAz_old = rAz

        alpha = rAz / np.inner(Ap.conjugate(), Ap)  # 3
        x += alpha * p                              # 4

        if np.mod(it, recompute_r) and it > 0:      # 5
            r -= alpha * Ap
        else:
            r = b - A @ x

        z = M @ r

        Az = A @ z
        rAz = np.inner(r.conjugate(), Az)

        beta = rAz/rAz_old                        # 6

        p *= beta                                 # 7
        p += z

        Ap *= beta                                # 8
        Ap += Az

        it += 1

        zz = np.inner(z.conjugate(), z)

        normr = np.linalg.norm(r)

        if residuals is not None:
            residuals.append(normr)

        if callback is not None:
            callback(x)

        # set the stopping criteria (see the docstring)
        if criteria == 'rr':
            rtol = tol * normb
        elif criteria == 'rr+':
            rtol = tol * (normA * np.linalg.norm(x) + normb)
        elif criteria == 'MrMr':
            normr = norm(z)
            rtol = tol * normMb

        if normr < rtol:
            return (postprocess(x), 0)

        if zz == 0.0:
            # rz == 0.0 is an indicator of convergence when r = 0.0
            warn("\nSingular preconditioner detected in CR, ceasing iterations\n")
            return (postprocess(x), -1)

        if it == maxiter:
            return (postprocess(x), it)

if __name__ == '__main__':
    # from numpy import diag
    # A = random((4,4))
    # A = A*A.transpose() + diag([10,10,10,10])
    # b = random((4,1))
    # x0 = random((4,1))

    from pyamg.gallery import stencil_grid
    from numpy.random import random
    import time
    from pyamg.krylov._gmres import gmres

    A = stencil_grid([[0, -1, 0], [-1, 4, -1], [0, -1, 0]], (100, 100),
                     dtype=float, format='csr')
    b = random((A.shape[0],))
    x0 = random((A.shape[0],))

    print('\n\nTesting CR with %d x %d 2D Laplace Matrix' %
          (A.shape[0], A.shape[0]))
    t1 = time.time()
    r = []
    (x, flag) = cr(A, b, x0, tol=1e-8, maxiter=100, residuals=r)
    t2 = time.time()
    print('{} took {:0.3f} ms'.format('cr', (t2-t1)*1000.0))
    print('norm = %g' % (norm(b - A*x)))
    print('info flag = %d' % (flag))

    t1 = time.time()
    r2 = []
    (x, flag) = gmres(A, b, x0, tol=1e-8, maxiter=100, residuals=r2)
    t2 = time.time()
    print('{} took {:0.3f} ms'.format('gmres', (t2-t1)*1000.0))
    print('norm = %g' % (norm(b - A*x)))
    print('info flag = %d' % (flag))

    # from scipy.sparse.linalg.isolve import cg as icg
    # t1=time.time()
    # (y,flag) = icg(A,b,x0,tol=1e-8,maxiter=100)
    # t2=time.time()
    # print '\n%s took %0.3f ms' % ('linalg cg', (t2-t1)*1000.0)
    # print 'norm = %g'%(norm(b - A*y))
    # print 'info flag = %d'%(flag)
