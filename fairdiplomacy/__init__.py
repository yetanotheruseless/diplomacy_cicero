#
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#

# Set up pydipcc for easy access
import sys
import dipcc
sys.modules["fairdiplomacy.pydipcc"] = dipcc  # Make imports from fairdiplomacy.pydipcc work

# Make pydipcc available directly from fairdiplomacy
pydipcc = dipcc
