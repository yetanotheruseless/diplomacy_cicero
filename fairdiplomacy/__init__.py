#
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#

# PyTorch 2.13 initializes its Python tensor type casters when torch is
# imported. pydipcc returns tensors directly, so load torch before the native
# extension to keep direct fairdiplomacy.pydipcc calls safe.
import torch as _torch

from . import pydipcc as pydipcc
