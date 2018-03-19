import unittest

import dynet as dy
import numpy as np

from xnmt.attender import MlpAttender, DotAttender
from xnmt.batcher import mark_as_batch, Mask, SrcBatcher
from xnmt.bridge import CopyBridge
from xnmt.decoder import MlpSoftmaxDecoder
from xnmt.embedder import SimpleWordEmbedder
from xnmt.eval_task import LossEvalTask
import xnmt.events
from xnmt.exp_global import ExpGlobal
from xnmt.input_reader import PlainTextReader
from xnmt.lstm import BiLSTMSeqTransducer
from xnmt.loss_calculator import LossCalculator
from xnmt.optimizer import AdamTrainer
from xnmt.param_collection import NonPersistentParamCollection
from xnmt.pyramidal import PyramidalLSTMSeqTransducer
import xnmt.training_regimen
from xnmt.translator import DefaultTranslator
from xnmt.vocab import Vocab

class TestTruncatedBatchTraining(unittest.TestCase):

  def setUp(self):
    xnmt.events.clear()
    self.exp_global = ExpGlobal(dynet_param_collection = NonPersistentParamCollection())

    self.src_reader = PlainTextReader()
    self.trg_reader = PlainTextReader()
    self.src_data = list(self.src_reader.read_sents("examples/data/head.ja"))
    self.trg_data = list(self.trg_reader.read_sents("examples/data/head.en"))

  def assert_single_loss_equals_batch_loss(self, model, pad_src_to_multiple=1):
    """
    Tests whether single loss equals batch loss.
    Truncating src / trg sents to same length so no masking is necessary
    """
    batch_size=5
    src_sents = self.src_data[:batch_size]
    src_min = min([len(x) for x in src_sents])
    src_sents_trunc = [s[:src_min] for s in src_sents]
    for single_sent in src_sents_trunc:
      single_sent[src_min-1] = Vocab.ES
      while len(single_sent)%pad_src_to_multiple != 0:
        single_sent.append(Vocab.ES)
    trg_sents = self.trg_data[:batch_size]
    trg_min = min([len(x) for x in trg_sents])
    trg_sents_trunc = [s[:trg_min] for s in trg_sents]
    for single_sent in trg_sents_trunc: single_sent[trg_min-1] = Vocab.ES

    single_loss = 0.0
    for sent_id in range(batch_size):
      dy.renew_cg()
      train_loss = model.calc_loss(src=src_sents_trunc[sent_id],
                                   trg=trg_sents_trunc[sent_id],
                                   loss_calculator=LossCalculator()).value()
      single_loss += train_loss

    dy.renew_cg()

    batched_loss = model.calc_loss(src=mark_as_batch(src_sents_trunc),
                                   trg=mark_as_batch(trg_sents_trunc),
                                   loss_calculator=LossCalculator()).value()
    self.assertAlmostEqual(single_loss, sum(batched_loss), places=4)

  def test_loss_model1(self):
    model = DefaultTranslator(
              src_reader=self.src_reader,
              trg_reader=self.trg_reader,
              src_embedder=SimpleWordEmbedder(self.exp_global, vocab_size=100),
              encoder=BiLSTMSeqTransducer(self.exp_global),
              attender=MlpAttender(self.exp_global),
              trg_embedder=SimpleWordEmbedder(self.exp_global, vocab_size=100),
              decoder=MlpSoftmaxDecoder(self.exp_global, vocab_size=100, bridge=CopyBridge(exp_global=self.exp_global, dec_layers=1)),
            )
    model.set_train(False)
    self.assert_single_loss_equals_batch_loss(model)

  def test_loss_model2(self):
    model = DefaultTranslator(
              src_reader=self.src_reader,
              trg_reader=self.trg_reader,
              src_embedder=SimpleWordEmbedder(self.exp_global, vocab_size=100),
              encoder=PyramidalLSTMSeqTransducer(self.exp_global, layers=3),
              attender=MlpAttender(self.exp_global),
              trg_embedder=SimpleWordEmbedder(self.exp_global, vocab_size=100),
              decoder=MlpSoftmaxDecoder(self.exp_global, vocab_size=100, bridge=CopyBridge(exp_global=self.exp_global, dec_layers=1)),
            )
    model.set_train(False)
    self.assert_single_loss_equals_batch_loss(model, pad_src_to_multiple=4)

  def test_loss_model3(self):
    model = DefaultTranslator(
              src_reader=self.src_reader,
              trg_reader=self.trg_reader,
              src_embedder=SimpleWordEmbedder(self.exp_global, vocab_size=100),
              encoder=BiLSTMSeqTransducer(self.exp_global, layers=3),
              attender=MlpAttender(self.exp_global),
              trg_embedder=SimpleWordEmbedder(self.exp_global, vocab_size=100),
              decoder=MlpSoftmaxDecoder(exp_global=self.exp_global, vocab_size=100, bridge=CopyBridge(exp_global=self.exp_global, dec_layers=1)),
            )
    model.set_train(False)
    self.assert_single_loss_equals_batch_loss(model)

  def test_loss_model4(self):
    model = DefaultTranslator(
              src_reader=self.src_reader,
              trg_reader=self.trg_reader,
              src_embedder=SimpleWordEmbedder(self.exp_global, vocab_size=100),
              encoder=BiLSTMSeqTransducer(self.exp_global),
              attender=DotAttender(self.exp_global),
              trg_embedder=SimpleWordEmbedder(self.exp_global, vocab_size=100),
              decoder=MlpSoftmaxDecoder(self.exp_global, vocab_size=100, bridge=CopyBridge(exp_global=self.exp_global, dec_layers=1)),
            )
    model.set_train(False)
    self.assert_single_loss_equals_batch_loss(model)

class TestBatchTraining(unittest.TestCase):

  def setUp(self):
    xnmt.events.clear()
    self.exp_global = ExpGlobal(dynet_param_collection = NonPersistentParamCollection())

    self.src_reader = PlainTextReader()
    self.trg_reader = PlainTextReader()
    self.src_data = list(self.src_reader.read_sents("examples/data/head.ja"))
    self.trg_data = list(self.trg_reader.read_sents("examples/data/head.en"))

  def assert_single_loss_equals_batch_loss(self, model, pad_src_to_multiple=1):
    """
    Tests whether single loss equals batch loss.
    Here we don't truncate the target side and use masking.
    """
    batch_size = 5
    src_sents = self.src_data[:batch_size]
    src_min = min([len(x) for x in src_sents])
    src_sents_trunc = [s[:src_min] for s in src_sents]
    for single_sent in src_sents_trunc:
      single_sent[src_min-1] = Vocab.ES
      while len(single_sent)%pad_src_to_multiple != 0:
        single_sent.append(Vocab.ES)
    trg_sents = self.trg_data[:batch_size]
    trg_max = max([len(x) for x in trg_sents])
    trg_masks = Mask(np.zeros([batch_size, trg_max]))
    for i in range(batch_size):
      for j in range(len(trg_sents[i]), trg_max):
        trg_masks.np_arr[i,j] = 1.0
    trg_sents_padded = [[w for w in s] + [Vocab.ES]*(trg_max-len(s)) for s in trg_sents]

    single_loss = 0.0
    for sent_id in range(batch_size):
      dy.renew_cg()
      train_loss = model.calc_loss(src=src_sents_trunc[sent_id],
                                   trg=trg_sents[sent_id],
                                   loss_calculator=LossCalculator()).value()
      single_loss += train_loss

    dy.renew_cg()

    batched_loss = model.calc_loss(src=mark_as_batch(src_sents_trunc),
                                   trg=mark_as_batch(trg_sents_padded, trg_masks),
                                   loss_calculator=LossCalculator()).value()
    self.assertAlmostEqual(single_loss, sum(batched_loss), places=4)

  def test_loss_model1(self):
    model = DefaultTranslator(
              src_reader=self.src_reader,
              trg_reader=self.trg_reader,
              src_embedder=SimpleWordEmbedder(exp_global=self.exp_global, vocab_size=100),
              encoder=BiLSTMSeqTransducer(exp_global=self.exp_global),
              attender=MlpAttender(exp_global=self.exp_global),
              trg_embedder=SimpleWordEmbedder(exp_global=self.exp_global, vocab_size=100),
              decoder=MlpSoftmaxDecoder(exp_global=self.exp_global, vocab_size=100, bridge=CopyBridge(exp_global=self.exp_global, dec_layers=1)),
            )
    model.set_train(False)
    self.assert_single_loss_equals_batch_loss(model)

  def test_loss_model2(self):
    model = DefaultTranslator(
              src_reader=self.src_reader,
              trg_reader=self.trg_reader,
              src_embedder=SimpleWordEmbedder(exp_global=self.exp_global, vocab_size=100),
              encoder=PyramidalLSTMSeqTransducer(exp_global=self.exp_global, layers=3),
              attender=MlpAttender(exp_global=self.exp_global),
              trg_embedder=SimpleWordEmbedder(exp_global=self.exp_global, vocab_size=100),
              decoder=MlpSoftmaxDecoder(exp_global=self.exp_global, vocab_size=100, bridge=CopyBridge(exp_global=self.exp_global, dec_layers=1)),
            )
    model.set_train(False)
    self.assert_single_loss_equals_batch_loss(model, pad_src_to_multiple=4)

  def test_loss_model3(self):
    model = DefaultTranslator(
              src_reader=self.src_reader,
              trg_reader=self.trg_reader,
              src_embedder=SimpleWordEmbedder(exp_global=self.exp_global, vocab_size=100),
              encoder=BiLSTMSeqTransducer(exp_global=self.exp_global, layers=3),
              attender=MlpAttender(exp_global=self.exp_global),
              trg_embedder=SimpleWordEmbedder(exp_global=self.exp_global, vocab_size=100),
              decoder=MlpSoftmaxDecoder(exp_global=self.exp_global, vocab_size=100, bridge=CopyBridge(exp_global=self.exp_global, dec_layers=1)),
            )
    model.set_train(False)
    self.assert_single_loss_equals_batch_loss(model)


class TestTrainDevLoss(unittest.TestCase):

  def setUp(self):
    xnmt.events.clear()

  def test_train_dev_loss_equal(self):
    self.exp_global = ExpGlobal(dynet_param_collection=NonPersistentParamCollection())
    batcher = SrcBatcher(batch_size=5, break_ties_randomly=False)
    train_args = {}
    train_args['src_file'] = "examples/data/head.ja"
    train_args['trg_file'] = "examples/data/head.en"
    train_args['loss_calculator'] = LossCalculator()
    train_args['model'] = DefaultTranslator(src_reader=PlainTextReader(),
                                            trg_reader=PlainTextReader(),
                                            src_embedder=SimpleWordEmbedder(exp_global=self.exp_global, vocab_size=100),
                                            encoder=BiLSTMSeqTransducer(exp_global=self.exp_global),
                                            attender=MlpAttender(exp_global=self.exp_global),
                                            trg_embedder=SimpleWordEmbedder(exp_global=self.exp_global, vocab_size=100),
                                            decoder=MlpSoftmaxDecoder(exp_global=self.exp_global, vocab_size=100, bridge=CopyBridge(exp_global=self.exp_global, dec_layers=1)),
                                            )
    train_args['dev_tasks'] = [LossEvalTask(model=train_args['model'],
                                            src_file="examples/data/head.ja",
                                            ref_file="examples/data/head.en",
                                            batcher=batcher)]
    train_args['trainer'] = None
    train_args['batcher'] = batcher
    train_args['run_for_epochs'] = 1
    training_regimen = xnmt.training_regimen.SimpleTrainingRegimen(exp_global=self.exp_global, **train_args)
    training_regimen.exp_global = self.exp_global
    training_regimen.run_training(save_fct = lambda: None, update_weights=False)
    self.assertAlmostEqual(training_regimen.logger.epoch_loss.sum() / training_regimen.logger.epoch_words,
                           training_regimen.logger.dev_score.loss, places=5)

class TestOverfitting(unittest.TestCase):

  def setUp(self):
    xnmt.events.clear()

  def test_overfitting(self):
    self.exp_global = ExpGlobal(dynet_param_collection = NonPersistentParamCollection(),
                                dropout = 0.0)
    self.exp_global.default_layer_dim = 16
    batcher = SrcBatcher(batch_size=10, break_ties_randomly=False)
    train_args = {}
    train_args['src_file'] = "examples/data/head.ja"
    train_args['trg_file'] = "examples/data/head.en"
    train_args['loss_calculator'] = LossCalculator()
    train_args['model'] = DefaultTranslator(src_reader=PlainTextReader(),
                                            trg_reader=PlainTextReader(),
                                            src_embedder=SimpleWordEmbedder(self.exp_global, vocab_size=100),
                                            encoder=BiLSTMSeqTransducer(self.exp_global),
                                            attender=MlpAttender(self.exp_global),
                                            trg_embedder=SimpleWordEmbedder(self.exp_global, vocab_size=100),
                                            decoder=MlpSoftmaxDecoder(self.exp_global, vocab_size=100, bridge=CopyBridge(exp_global=self.exp_global, dec_layers=1)),
                                            )
    train_args['dev_tasks'] = [LossEvalTask(model=train_args['model'],
                                            src_file="examples/data/head.ja",
                                            ref_file="examples/data/head.en",
                                            batcher=batcher)]
    train_args['run_for_epochs'] = 1
    train_args['trainer'] = AdamTrainer(self.exp_global, alpha=0.1)
    train_args['batcher'] = batcher
    training_regimen = xnmt.training_regimen.SimpleTrainingRegimen(exp_global=self.exp_global, **train_args)
    training_regimen.exp_global = self.exp_global
    for _ in range(50):
      training_regimen.run_training(save_fct=lambda:None, update_weights=True)
    self.assertAlmostEqual(0.0,
                           training_regimen.logger.epoch_loss.sum() / training_regimen.logger.epoch_words,
                           places=2)

if __name__ == '__main__':
  unittest.main()
