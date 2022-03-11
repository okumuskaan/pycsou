import typing as typ

import numpy as np

import pycsou.abc.operator as pyco
import pycsou.abc.solver as pycs
import pycsou.opt.stop as pycos
import pycsou.runtime as pycrt
import pycsou.util as pycu
import pycsou.util.ptype as pyct


class CG(pycs.Solver):
    r"""
    Conjugate Gradient Method.

    The Conjugate Gradient method solves the minimization problem

    .. math::

       \min_{x\in\mathbb{R}^{N}} \frac{1}{2} \mathbf{x}^{T} \mathbf{A} \mathbf{x} - \mathbf{x}^{T} \mathbf{b},

    where :math:`\mathbf{A}: \mathbb{R}^{N} \to \mathbb{R}^{N}` is a *symmetric* *positive definite*
    operator, and :math:`\mathbf{b} \in \mathbb{R}^{N}`.


    ``CG.fit()`` **Parameterization**

    b: NDArray
        (..., N) 'b' terms in the CG cost function. All problems are solved in parallel.
    x0: NDArray
       (..., N) initial point(s). Defaults to 0 if unspecified.
    """

    def __init__(
        self,
        A: pyco.PosDefOp,
        *,
        folder: typ.Optional[pyct.PathLike] = None,
        exist_ok: bool = False,
        writeback_rate: typ.Optional[int] = None,
        verbosity: int = 1,
        show_progress: bool = True,
        log_var: pyct.VarName = ("x",),
    ):
        super().__init__(
            folder=folder,
            exist_ok=exist_ok,
            writeback_rate=writeback_rate,
            verbosity=verbosity,
            show_progress=show_progress,
            log_var=log_var,
        )

        self._A = A

    def m_init(
        self,
        b: pyct.NDArray,
        x0: pyct.NDArray = None,
    ):
        mst = self._mstate  # shorthand

        mst["b"] = b = pycrt.coerce(b)
        xp = pycu.get_array_module(b)
        if x0 is None:
            mst["x"] = xp.zeros_like(b)
        else:
            mst["x"] = pycrt.coerce(x0)

        # 2-stage res-computation guarantees RT-precision in case apply() not
        # enforce_precision()-ed.
        mst["residual"] = xp.zeros_like(b)
        mst["residual"][:] = b - self._A.apply(mst["x"])
        mst["conjugate_dir"] = mst["residual"].copy()

    def m_step(self):
        mst = self._mstate  # shorthand
        x, r, p = mst["x"], mst["residual"], mst["conjugate_dir"]
        xp = pycu.get_array_module(x)

        Ap = self._A.apply(p)
        rr = xp.linalg.norm(r, ord=2, axis=-1, keepdims=True) ** 2
        alpha = rr / (p * Ap).sum(axis=-1, keepdims=True)
        x += alpha * p
        r -= alpha * Ap
        beta = xp.linalg.norm(r, ord=2, axis=-1, keepdims=True) ** 2 / rr
        p *= beta
        p += r

        # for homogenity with other solver code. Optional in CG due to in-place computations.
        mst["x"], mst["residual"], mst["conjugate_dir"] = x, r, p

    def default_stop_crit(self) -> pycs.StoppingCriterion:
        def explicit_residual(x):
            mst = self._mstate  # shorthand
            residual = mst["b"].copy()
            residual -= self._A.apply(x)
            return residual

        stop_crit = pycos.AbsError(
            eps=1e-4,
            var="x",
            f=explicit_residual,
            norm=2,
            satisfy_all=True,
        )
        return stop_crit

    def solution(self) -> pyct.NDArray:
        """
        Returns
        -------
        p: NDArray
            (..., N) solution.
        """
        data, _ = self.stats()
        return data.get("x")
