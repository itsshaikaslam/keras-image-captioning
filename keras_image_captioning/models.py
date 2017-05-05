from keras.applications.inception_v3 import InceptionV3
from keras.models import Model
from keras.layers import (Dense, Embedding, GRU, Input, LSTM, RepeatVector,
                          TimeDistributed)
from keras.layers.merge import Concatenate
from keras.layers.wrappers import Bidirectional
from keras.optimizers import Adam

from .config import active_config
from .losses import categorical_crossentropy_from_logits
from .metrics import categorical_accuracy_with_variable_timestep


class ImageCaptioningModel(object):
    def __init__(self,
                 learning_rate=None,
                 vocab_size=None,
                 embedding_size=None,
                 rnn_output_size=None,
                 dropout_rate=None,
                 bidirectional_rnn=None,
                 rnn_type=None):
        """
        If an arg is None, it will get its value from config.active_config.
        """
        self._learning_rate = learning_rate or active_config().learning_rate
        self._vocab_size = vocab_size or active_config().vocab_size
        self._embedding_size = embedding_size or active_config().embedding_size
        self._rnn_output_size = (rnn_output_size or
                                 active_config().rnn_output_size)
        self._dropout_rate = dropout_rate or active_config().dropout_rate
        self._rnn_type = rnn_type or active_config().rnn_type

        if bidirectional_rnn is None:
            self._bidirectional_rnn = active_config().bidirectional_rnn
        else:
            self._bidirectional_rnn = bidirectional_rnn

        self._keras_model = None

        if self._vocab_size is None:
            raise ValueError('config.active_config().vocab_size cannot be '
                             'None! You should check your config or you can '
                             'explicitly pass the vocab_size argument.')

        if self._rnn_type not in ('lstm', 'gru'):
            raise ValueError('rnn_type must be either "lstm" or "gru"!')

    @property
    def keras_model(self):
        if self._keras_model is None:
            raise AttributeError('Execute build method first before accessing '
                                 'keras_model!')
        return self._keras_model

    def build(self):
        if self._keras_model:
            return

        image_input, image_embedding = self._build_image_embedding()
        sentence_input, word_embedding = self._build_word_embedding()
        sequence_input = Concatenate(axis=1)([image_embedding, word_embedding])
        sequence_output = self._build_sequence_model(sequence_input)

        model = Model(inputs=[image_input, sentence_input],
                      outputs=sequence_output)
        model.compile(optimizer=Adam(lr=self._learning_rate),
                      loss=categorical_crossentropy_from_logits,
                      metrics=[categorical_accuracy_with_variable_timestep])

        self._keras_model = model

    def _build_image_embedding(self):
        image_model = InceptionV3(include_top=False, weights='imagenet',
                                  pooling='avg')
        for layer in image_model.layers:
            layer.trainable = False

        image_dense = Dense(units=self._embedding_size)(image_model.output)
        # Add timestep dimension
        image_embedding = RepeatVector(1)(image_dense)

        image_input = image_model.input
        return image_input, image_embedding

    def _build_word_embedding(self):
        sentence_input = Input(shape=[None])
        word_embedding = Embedding(input_dim=self._vocab_size,
                            output_dim=self._embedding_size)(sentence_input)
        return sentence_input, word_embedding

    def _build_sequence_model(self, sequence_input):
        RNN = GRU if self._rnn_type == 'gru' else LSTM
        rnn = RNN(units=self._rnn_output_size,
                  return_sequences=True,
                  dropout=self._dropout_rate,
                  recurrent_dropout=self._dropout_rate,
                  implementation=2)

        rnn = Bidirectional(rnn) if self._bidirectional_rnn else rnn
        rnn = rnn(sequence_input)
        time_dist_dense = TimeDistributed(Dense(units=self._vocab_size))(rnn)

        return time_dist_dense
