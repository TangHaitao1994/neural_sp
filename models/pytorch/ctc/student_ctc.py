#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Student CTC model."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

try:
    from warpctc_pytorch import CTCLoss
except:
    raise ImportError('Install warpctc_pytorch.')

import torch.nn as nn
import torch.nn.functional as F

from models.pytorch.ctc.ctc import CTC, _concatenate_labels
from utils.io.variable import np2var, var2np

NEG_INF = -float("inf")
LOG_0 = NEG_INF
LOG_1 = 0


class StudentCTC(CTC):
    """Student CTC model.
    Args:
        input_size (int): the dimension of input features
        encoder_type (string): the type of the encoder. Set lstm or gru or rnn.
        bidirectional (bool): if True create a bidirectional encoder
        num_units (int): the number of units in each layer
        num_proj (int): the number of nodes in recurrent projection layer
        num_layers (int): the number of layers of the encoder of the main task
        dropout (float): the probability to drop nodes
        main_loss_weight (float): A weight parameter for the main CTC loss
        num_classes (int): the number of classes of target labels of the main task
            (excluding a blank class)
        parameter_init (float, optional): Range of uniform distribution to
            initialize weight parameters
        subsample_list (list, optional): subsample in the corresponding layers (True)
            ex.) [False, True, True, False] means that subsample is conducted
                in the 2nd and 3rd layers.
        logits_temperature (float):
        num_stack (int, optional): the number of frames to stack
        splice (int, optional): frames to splice. Default is 1 frame.
        conv_channels (list, optional):
        conv_kernel_sizes (list, optional):
        conv_strides (list, optional):
        poolings (list, optional):
        activation (string, optional): The activation function of CNN layers.
            Choose from relu or prelu or hard_tanh
        batch_norm (bool, optional):
        weight_noise_std (flaot, optional):
    """

    def __init__(self,
                 input_size,
                 encoder_type,
                 bidirectional,
                 num_units,
                 num_proj,
                 num_layers,
                 fc_list,
                 dropout,
                 main_loss_weight,  # ***
                 num_classes,
                 parameter_init=0.1,
                 subsample_list=[],
                 logits_temperature=1,
                 num_stack=1,
                 splice=1,
                 conv_channels=[],
                 conv_kernel_sizes=[],
                 conv_strides=[],
                 poolings=[],
                 activation='relu',
                 batch_norm=False,
                 weight_noise_std=0):

        super(StudentCTC, self).__init__(
            input_size=input_size,  # 120 or 123
            encoder_type=encoder_type,
            bidirectional=bidirectional,
            num_units=num_units,
            num_proj=num_proj,
            num_layers=num_layers,
            dropout=dropout,
            num_classes=num_classes,
            parameter_init=parameter_init,
            subsample_list=subsample_list,
            fc_list=fc_list,
            logits_temperature=logits_temperature,
            batch_norm=batch_norm,
            weight_noise_std=weight_noise_std)

        # Weight parameter for MTL with XE loss
        self.main_loss_weight = main_loss_weight

        if len(fc_list) > 0:
            self.fc_xe = nn.Linear(
                fc_list[-1], self.num_classes)
        else:
            self.fc_xe = nn.Linear(
                num_units * self.num_directions, self.num_classes)

    def forward(self, inputs, labels, labels_xe, inputs_seq_len,
                labels_seq_len, volatile=False):
        """Forward computation.
        Args:
            inputs (np.ndarray): A tensor of size `[B, T_in, input_size]`
            labels (np.ndarray): A tensor of size `[B, T_out]`
            labels_xe (np.ndarray): A tensor of size `[B, T_out_sub]`
            inputs_seq_len (np.ndarray): A tensor of size `[B]`
            labels_seq_len (np.ndarray): A tensor of size `[B]`
            volatile (bool, optional): if True, the history will not be saved.
                This should be used in inference model for memory efficiency.
        Returns:
            loss (FloatTensor): A tensor of size `[1]`
            loss_main (FloatTensor): A tensor of size `[1]`
            loss_sub (FloatTensor): A tensor of size `[1]`
        """
        # Wrap by Variable
        inputs_var = np2var(inputs, use_cuda=self.use_cuda)
        labels_var = np2var(labels, dtype='int', use_cuda=False)
        labels_xe_var = np2var(labels_xe, dtype='float', use_cuda=False)
        inputs_seq_len_var = np2var(
            inputs_seq_len, dtype='int', use_cuda=self.use_cuda)
        labels_seq_len_var = np2var(
            labels_seq_len, dtype='int', use_cuda=False)

        labels_var = labels_var + 1
        # NOTE: index 0 is reserved for blank in warpctc_pytorch

        # Encode acoustic features
        logits, logits_xe, perm_indices = self._encode(
            inputs_var, inputs_seq_len_var, volatile=volatile)

        # Permutate indices
        if perm_indices is not None:
            labels_var = labels_var[perm_indices.cpu()]
            labels_xe_var = labels_xe_var[perm_indices.cpu()]
            inputs_seq_len_var = inputs_seq_len_var[perm_indices]
            labels_seq_len_var = labels_seq_len_var[perm_indices.cpu()]

        # Concatenate all labels for warpctc_pytorch
        # `[B, T_out]` -> `[1,]`
        concatenated_labels = _concatenate_labels(
            labels_var, labels_seq_len_var)

        # Output smoothing
        if self.logits_temperature != 1:
            logits /= self.logits_temperature
            logits_xe /= self.logits_temperature

        # Modify inputs_seq_len for reducing time resolution
        if self.encoder.conv is not None or self.encoder_type == 'cnn':
            for i in range(len(inputs_seq_len)):
                inputs_seq_len_var.data[i] = self.encoder.conv_out_size(
                    inputs_seq_len_var.data[i], 1)
        inputs_seq_len_var /= 2 ** sum(self.subsample_list)
        # NOTE: floor is not needed because inputs_seq_len_var is IntTensor

        # Compute CTC loss and XE loss
        ctc_loss_fn = CTCLoss()
        loss_main = ctc_loss_fn(logits, concatenated_labels,
                                inputs_seq_len_var.cpu(), labels_seq_len_var)
        loss_xe = F.cross_entropy(logits_xe, labels_xe,
                                  size_average=False)
        loss = loss_main * self.main_loss_weight + \
            loss_xe * (1 - self.main_loss_weight)

        # Average the loss by mini-batch
        batch_size = logits.size(1)
        loss /= batch_size

        return (loss, loss_main * self.main_loss_weight / batch_size,
                loss_xe * (1 - self.main_loss_weight) / batch_size)

    def _encode(self, inputs, inputs_seq_len, volatile):
        """Encode acoustic features.
        Args:
            inputs (FloatTensor): A tensor of size `[B, T, input_size]`
            inputs_seq_len (IntTensor): A tensor of size `[B]`
            volatile (bool): if True, the history will not be saved.
                This should be used in inference model for memory efficiency.
        Returns:
            logits (FloatTensor): A tensor of size
                `[T, B, num_classes (including blank)]`
            logits_xe (FloatTensor): A tensor of size
                `[T, B, num_classes_sub (including blank)]`
            perm_indices (LongTensor):
        """
        if self.encoder_type != 'cnn':
            encoder_outputs, _, perm_indices = self.encoder(
                inputs, inputs_seq_len, volatile, mask_sequence=True)
        else:
            encoder_outputs = self.encoder(inputs)
            # NOTE: `[B, T, feature_dim]`
            encoder_outputs = encoder_outputs.transpose(0, 1).contiguous()
            perm_indices = None

        # Convert to 2D tensor
        max_time, batch_size = encoder_outputs.size()[:2]
        encoder_outputs = encoder_outputs.view(max_time * batch_size, -1)
        # contiguous()

        if len(self.fc_list) > 0:
            encoder_outputs = self.fc_layers(encoder_outputs)
        logits = self.fc(encoder_outputs)
        logits_xe = self.fc_xe(encoder_outputs)

        # Reshape back to 3D tensor
        logits = logits.view(max_time, batch_size, -1)
        logits_xe = logits_xe.view(max_time, batch_size, -1)

        return logits, logits_xe, perm_indices

    def decode_xe(self, inputs, inputs_seq_len, beam_width=1):
        """
        Args:
            inputs (np.ndarray): A tensor of size `[B, T_in, input_size]`
            inputs_seq_len (np.ndarray): A tensor of size `[B]`
            beam_width (int, optional): the size of beam
        Returns:
            best_hyps (np.ndarray):
        """
        # Wrap by Variable
        inputs_var = np2var(inputs, use_cuda=self.use_cuda, volatile=True)
        inputs_seq_len_var = np2var(
            inputs_seq_len, dtype='int', use_cuda=self.use_cuda, volatile=True)

        # Encode acoustic features
        _, logits_xe, perm_indices = self._encode(
            inputs_var, inputs_seq_len_var, volatile=True)

        # Permutate indices
        if perm_indices is not None:
            perm_indices = var2np(perm_indices)
            inputs_seq_len_var = inputs_seq_len_var[perm_indices]

        # Convert to batch-major
        logits_xe = logits_xe.transpose(0, 1)

        # Modify inputs_seq_len for reducing time resolution
        if self.encoder.conv is not None or self.encoder_type == 'cnn':
            for i in range(len(inputs_seq_len)):
                inputs_seq_len_var.data[i] = self.encoder.conv_out_size(
                    inputs_seq_len_var.data[i], 1)
        inputs_seq_len_var /= 2 ** sum(self.subsample_list)
        # NOTE: floor is not needed because inputs_seq_len_var is IntTensor

        log_probs_xe = F.log_softmax(logits_xe, dim=logits_xe.dim() - 1)

        if beam_width == 1:
            best_hyps = self._decode_greedy_np(
                var2np(log_probs_xe), var2np(inputs_seq_len_var))
        else:
            best_hyps = self._decode_beam_np(
                var2np(log_probs_xe), var2np(inputs_seq_len_var),
                beam_width=beam_width)

        best_hyps = best_hyps - 1
        # NOTE: index 0 is reserved for blank in warpctc_pytorch

        # Permutate indices to the original order
        if perm_indices is not None:
            best_hyps = best_hyps[perm_indices]

        return best_hyps
