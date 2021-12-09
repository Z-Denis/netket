# Copyright 2021 The NetKet Authors - All rights reserved.
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

from typing import List, Tuple, Optional, Union, Iterator
from textwrap import dedent

import numpy as np

from .abstract_hilbert import AbstractHilbert

max_states = np.iinfo(np.int32).max
"""int: Maximum number of states that can be indexed"""


def _is_indexable(shape):
    """
    Returns whether a discrete Hilbert space of shape `shape` is
    indexable (i.e., its total number of states is below the maximum).
    """
    log_max = np.log(max_states)
    return np.sum(np.log(shape)) <= log_max


class NoneTypeT:
    pass


NoneType = NoneTypeT()


legacy_warn_str = (
    "This choice of arguments for `hilbert.random_state` is deprecated and "
    "will be removed in a future version.\n"
    "The new syntax is\n"
    "    hilbert.random_state(prngkey, size=1, dtype=jnp.float32)\n"
    "and, like in `jax.random`, the first argument is mandatory and must be a valid jax `PRNGKey`."
    "Results may differ between the states generated by the legacy, "
    "deprecated code and the new one. Note that the old code does not "
    "support defining custom methods."
)


class DiscreteHilbert(AbstractHilbert):
    """Abstract class for an hilbert space defined on a lattice.

    This class definese the common interface that can be used to
    interact with hilbert spaces on lattices.
    """

    def __init__(self, shape: Tuple[int, ...]):
        """
        Initializes a discrete Hilbert space with a basis of given shape.

        Args:
            shape: The local dimension of the Hilbert space for each degree
                of freedom.
        """
        self._shape = shape

        super().__init__()

    @property
    def shape(self) -> Tuple[int, ...]:
        r"""The size of the hilbert space on every site."""
        return self._shape

    @property
    def is_finite(self) -> bool:
        r"""Whether the local hilbert space is finite."""
        raise NotImplementedError(  # pragma: no cover
            dedent(
                f"""
            `is_finite` is not implemented for discrete hilbert
            space {type(self)}.
            """
            )
        )

    @property
    def n_states(self) -> int:
        r"""The total dimension of the many-body Hilbert space.
        Throws an exception iff the space is not indexable."""
        raise NotImplementedError(  # pragma: no cover
            dedent(
                f"""
            `n_states` is not implemented for discrete hilbert
            space {type(self)}.
            """
            )
        )

    def size_at_index(self, i: int) -> int:
        r"""Size of the local degrees of freedom for the i-th variable.

        Args:
            i: The index of the desired site

        Returns:
            The number of degrees of freedom at that site
        """
        return self.shape[i]  # pragma: no cover

    def states_at_index(self, i: int) -> Optional[List[float]]:
        r"""A list of discrete local quantum numbers at the site i.
        If the local states are infinitely many, None is returned.

        Args:
            i: The index of the desired site.

        Returns:
            A list of values or None if there are infintely many.
        """
        raise NotImplementedError()  # pragma: no cover

    def numbers_to_states(
        self, numbers: Union[int, np.ndarray], out: Optional[np.ndarray] = None
    ) -> np.ndarray:
        r"""Returns the quantum numbers corresponding to the n-th basis state
        for input n. n is an array of integer indices such that
        :code:`numbers[k]=Index(states[k])`.
        Throws an exception iff the space is not indexable.

        Args:
            numbers (numpy.array): Batch of input numbers to be converted into arrays of
                quantum numbers.
            out: Optional Array of quantum numbers corresponding to numbers.
        """
        if out is None:
            out = np.empty((np.atleast_1d(numbers).shape[0], self.size))

        if np.any(numbers >= self.n_states):
            raise ValueError("numbers outside the range of allowed states")

        if np.isscalar(numbers):
            return self._numbers_to_states(np.atleast_1d(numbers), out=out)[0, :]
        else:
            return self._numbers_to_states(numbers, out=out)

    def states_to_numbers(
        self, states: np.ndarray, out: Optional[np.ndarray] = None
    ) -> Union[int, np.ndarray]:
        r"""Returns the basis state number corresponding to given quantum states.
        The states are given in a batch, such that states[k] has shape (hilbert.size).
        Throws an exception iff the space is not indexable.

        Args:
            states: Batch of states to be converted into the corresponding integers.
            out: Array of integers such that out[k]=Index(states[k]).
                 If None, memory is allocated.

        Returns:
            numpy.darray: Array of integers corresponding to out.
        """
        if states.shape[-1] != self.size:
            raise ValueError(
                f"Size of this state ({states.shape[-1]}) not"
                f"corresponding to this hilbert space {self.size}"
            )

        states_r = np.asarray(np.reshape(states, (-1, states.shape[-1])))

        if out is None:
            out = np.empty(states_r.shape[:-1], dtype=np.int64)

        out = self._states_to_numbers(states_r, out=out.reshape(-1))

        if states.ndim == 1:
            return out[0]
        else:
            return out.reshape(states.shape[:-1])

    def states(self) -> Iterator[np.ndarray]:
        r"""Returns an iterator over all valid configurations of the Hilbert space.
        Throws an exception iff the space is not indexable.
        Iterating over all states with this method is typically inefficient,
        and ```all_states``` should be prefered.

        """
        for i in range(self.n_states):
            yield self.numbers_to_states(i).reshape(-1)

    def all_states(self, out: Optional[np.ndarray] = None) -> np.ndarray:
        r"""Returns all valid states of the Hilbert space.

        Throws an exception if the space is not indexable.

        Args:
            out: an optional pre-allocated output array

        Returns:
            A (n_states x size) batch of statess. this corresponds
            to the pre-allocated array if it was passed.
        """
        numbers = np.arange(0, self.n_states, dtype=np.int64)

        return self.numbers_to_states(numbers, out)

    @property
    def is_indexable(self) -> bool:
        """Whever the space can be indexed with an integer"""
        if not self.is_finite:
            return False
        return _is_indexable(self.shape)

    def __mul__(self, other: "DiscreteHilbert"):
        if self == other:
            return self ** 2
        else:
            from .tensor_hilbert import TensorHilbert

            if type(self) == type(other):
                res = self._mul_sametype_(other)
                if res is not NotImplemented:
                    return res

            return TensorHilbert(self) * other