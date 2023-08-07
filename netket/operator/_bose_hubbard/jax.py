# Copyright 2023 The NetKet Authors - All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from functools import partial, wraps
from typing import Optional

import jax
from jax import numpy as jnp
from jax.tree_util import register_pytree_node_class

from netket.graph import AbstractGraph
from netket.hilbert import Fock
from netket.utils.types import DType

from .._discrete_operator_jax import DiscreteJaxOperator

from .base import BoseHubbardBase


@register_pytree_node_class
class BoseHubbardJax(BoseHubbardBase, DiscreteJaxOperator):
    @wraps(BoseHubbardBase.__init__)
    def __init__(
        self,
        hilbert: Fock,
        graph: AbstractGraph,
        U: float,
        V: float = 0.0,
        J: float = 1.0,
        mu: float = 0.0,
        dtype: Optional[DType] = None,
    ):
        U = jnp.array(U, dtype=dtype)
        V = jnp.array(V, dtype=dtype)
        J = jnp.array(J, dtype=dtype)
        mu = jnp.array(mu, dtype=dtype)

        super().__init__(hilbert, graph=graph, U=U, V=V, J=J, mu=mu, dtype=dtype)

        self._edges = jnp.asarray(self.edges, dtype=jnp.int32)
        self._n_max = tuple(self.hilbert.n_max)

    # @jax.jit
    # @wraps(BoseHubbardBase.n_conn)
    # def n_conn(self, x):
    #     return _bose_hubbard_n_conn_jax(x, self._edges, self.U, self.V, self.J, self.mu)

    @jax.jit
    @wraps(BoseHubbardBase.get_conn_padded)
    def get_conn_padded(self, x):
        return _bose_hubbard_kernel_jax(
            x, self._edges, self.U, self.V, self.J, self.mu, self._n_max
        )

    # def to_numba_operator(self) -> "BoseHubbard":  # noqa: F821
    #     """
    #     Returns the standard (numba) version of this operator, which is an
    #     instance of {class}`nk.operator.BoseHubbard`.
    #     """
    #
    #     from .numba import BoseHubbard
    #
    #     return BoseHubbard(
    #         self.hilbert, graph=self.edges, U=self.U, V=self.V, J=self.J, mu=self.mu, dtype=self.dtype
    #     )

    def tree_flatten(self):
        data = (self.U, self.V, self.J, self.mu, self.edges)
        metadata = {"hilbert": self.hilbert, "dtype": self.dtype}
        return data, metadata

    @classmethod
    def tree_unflatten(cls, metadata, data):
        U, V, J, mu, edges = data
        hi = metadata["hilbert"]
        dtype = metadata["dtype"]

        return cls(hi, U=U, V=V, J=J, mu=mu, graph=edges, dtype=dtype)


@partial(jax.jit, static_argnames="n_max")
def _bose_hubbard_kernel_jax(x, edges, U, V, J, mu, n_max):
    i = edges[:, 0]
    j = edges[:, 1]
    n_i = x[:, i]
    n_j = x[:, j]

    Uh = 0.5 * U

    x_prime0 = x[:, None]
    mels0 = 0
    mels0 -= mu * x.sum(axis=-1, keepdims=True)
    mels0 += Uh * (x * (x - 1)).sum(axis=-1, keepdims=True)
    mels0 += V * (n_i * n_j).sum(axis=-1, keepdims=True)
    mask0 = jnp.full((x.shape[0], 1), True)

    # destroy on i create on j
    mask1 = (n_i > 0) & (n_j < n_max)
    mels1 = mask1 * (-J * jnp.sqrt(n_i) * jnp.sqrt(n_j + 1))
    x_prime1 = x[:, None] * mask1[..., None]
    x_prime1 = x_prime1.at[:, :, i].add(-1)
    x_prime1 = x_prime1.at[:, :, j].add(+1)

    # destroy on j create on i
    mask2 = (n_j > 0) & (n_i < n_max)
    mels2 = mask2 * (-J * jnp.sqrt(n_j) * jnp.sqrt(n_i + 1))
    x_prime2 = x[:, None] * mask2[..., None]
    x_prime2 = x_prime2.at[:, :, j].add(-1)
    x_prime2 = x_prime2.at[:, :, i].add(+1)

    mask_all = jnp.concatenate([mask0, mask1, mask2], axis=-1)
    mels_all = jnp.concatenate([mels0, mels1, mels2], axis=-1)
    xp_all = jnp.concatenate([x_prime0, x_prime1, x_prime2], axis=-2)
    return xp_all, mels_all, mask_all
