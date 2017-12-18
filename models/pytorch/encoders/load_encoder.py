#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Load each encoder."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from models.pytorch.encoders.rnn import RNNEncoder
from models.pytorch.encoders.pyramid_rnn import PyramidRNNEncoder
from models.pytorch.encoders.hierarchical_rnn import HierarchicalRNNEncoder
from models.pytorch.encoders.hierarchical_pyramid_rnn import HierarchicalPyramidRNNEncoder
# from models.pytorch.encoders.cnn import CNNEncoder
from models.pytorch.encoders.cnn_v2 import CNNEncoder

# from models.pytorch.encoders.resnet import ResNetEncoder


ENCODERS = {
    "lstm": RNNEncoder,
    "gru": RNNEncoder,
    "rnn": RNNEncoder,
    "plstm": PyramidRNNEncoder,
    "pgru": PyramidRNNEncoder,
    "prnn": PyramidRNNEncoder,
    "lstm_hierarchical": HierarchicalRNNEncoder,
    "gru_hierarchical": HierarchicalRNNEncoder,
    "rnn_hierarchical": HierarchicalRNNEncoder,
    "plstm_hierarchical": HierarchicalPyramidRNNEncoder,
    "pgru_hierarchical": HierarchicalPyramidRNNEncoder,
    "prnn_hierarchical": HierarchicalPyramidRNNEncoder,
    "cnn": CNNEncoder,
    # "resnet": ResNetEncoder,
}


def load(encoder_type):
    """Load an encoder.
    Args:
        encoder_type (string): name of the encoder in the key of ENCODERS
    Returns:
        model (nn.Module): An encoder class
    """
    if encoder_type not in ENCODERS:
        raise TypeError(
            "encoder_type should be one of [%s], you provided %s." %
            (", ".join(ENCODERS), encoder_type))
    return ENCODERS[encoder_type]
