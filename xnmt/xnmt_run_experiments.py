"""
Reads experiments descriptions in the passed configuration file
and runs them sequentially, logging outputs to files called <experimentname>.log
and <experimentname>.err.log, and reporting on final perplexity metrics.
"""

import configparser
import argparse
import sys
import encoder
import residual
import dynet as dy
import xnmt_train


class Tee:
  """
  Emulates a standard output or error streams. Calls to write on that stream will result
  in printing to stdout as well as logging to a file.
  """

  def __init__(self, name, indent=0, error=False):
    self.file = open(name, 'w')
    self.stdstream = sys.stderr if error else sys.stdout
    self.indent = indent
    self.error = error
    if error:
      sys.stderr = self
    else:
      sys.stdout = self

  def close(self):
    if self.error:
      sys.stderr = self.stdstream
    else:
      sys.stdout = self.stdstream
    self.file.close()

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    self.close()

  def write(self, data):
    self.file.write(data)
    self.stdstream.write(" " * self.indent + data)

  def flush(self):
    self.file.flush()
    self.stdstream.flush()


def get_or_none(key, dict, default_dict):
  return dict.get(key, default_dict.get(key, None))


def get_or_error(key, dict, default_dict):
  if key in dict:
    return dict[key]
  elif key in default_dict:
    return default_dict[key]
  else:
    raise RuntimeError("No value (or default value) passed for parameter {}".format(key))


if __name__ == '__main__':
  argparser = argparse.ArgumentParser()
  argparser.add_argument('experiments_file')
  argparser.add_argument('--dynet_mem', type=int)
  args = argparser.parse_args()

  config = configparser.ConfigParser()
  config.read(args.experiments_file)

  defaults = {"minibatch_size": None, "encoder_layers": 2, "decoder_layers": 2,
              "encoder_type": "BiLSTM", "run_for_epochs": 10, "eval_every": 1000,
              "batch_strategy": "src", "decoder_type": "LSTM", "model_file": "model.out"}

  if "defaults" in config.sections():
    defaults.update(config["defaults"])

  del config["defaults"]

  results = []

  for experiment in config.sections():
    print("=> Running {}".format(experiment))

    output = Tee(experiment + ".log", 3)
    err_output = Tee(experiment + ".err.log", 3, error=True)
    print("> Training")

    c = config[experiment]

    encoder_type = get_or_error("encoder_type", c, defaults).lower()
    if encoder_type == "BiLSTM".lower():
      encoder_builder = encoder.BiLSTMEncoder
    elif encoder_type == "ResidualLSTM".lower():
      encoder_builder = encoder.ResidualLSTMEncoder
    elif encoder_type == "ResidualBiLSTM".lower():
      encoder_builder = encoder.ResidualBiLSTMEncoder
    else:
      raise RuntimeError("Unkonwn encoder type {}".format(encoder_type))

    decoder_type = get_or_error("decoder_type", c, defaults).lower()
    if decoder_type == "LSTM".lower():
      decoder_builder = dy.LSTMBuilder
    elif decoder_type == "ResidualLSTM".lower():
      decoder_builder = residual.ResidualRNNBuilder
    else:
      raise RuntimeError("Unkonwn decoder type {}".format(encoder_type))

    # Simulate command-line arguments
    class Args: pass

    args = Args()
    minibatch_size = get_or_error("minibatch_size", c, defaults)
    args.minibatch_size = int(minibatch_size) if minibatch_size is not None else None
    args.eval_every = int(get_or_error("eval_every", c, defaults))
    args.batch_strategy = get_or_error("batch_strategy", c, defaults)
    args.train_source = get_or_error("train_source", c, defaults)
    args.train_target = get_or_error("train_target", c, defaults)
    args.dev_source = get_or_error("dev_source", c, defaults)
    args.dev_target = get_or_error("dev_target", c, defaults)
    args.model_file = get_or_error("model_file", c, defaults)

    train_ppl, dev_ppl = xnmt_train.xnmt_train(args,
                                          float(get_or_error("run_for_epochs", c, defaults)),
                                          encoder_builder,
                                          get_or_error("encoder_layers", c, defaults),
                                          decoder_builder,
                                          get_or_error("decoder_layers", c, defaults))

    print("Train perplexity: {}".format(train_ppl))
    print("Dev perplexity: {}".format(dev_ppl))

    results.append([experiment, train_ppl, dev_ppl])

    output.close()
    err_output.close()

  print("{:<20}|{:<20}|{:<20}".format("Experiment", "Train Perplexity", "Dev Perplexity"))
  print("-"*(20*3+2))

  for line in results:
    experiment, train_ppl, dev_ppl, = line
    print("{:<20}|{:>20}|{:>20}".format(experiment, train_ppl, dev_ppl))
