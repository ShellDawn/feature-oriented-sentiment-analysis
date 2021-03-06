#!/usr/bin/env python3

"""
Main code of the algorithm divided into the following parts :

    - preprocessing
    - feature extraction : TODO
    - polarity learning
    - prediction
    - Cross-validation : TODO

There is also a word representation part (TODO) using in the feature
extraction and polarity learning parts.

Based on the following tutorial & code :
    http://www.wildml.com/2015/12/implementing-a-cnn-for-text-classification-in-tensorflow/
    https://github.com/cahya-wirawan/cnn-text-classification-tf
"""

import tensorflow as tf
from tensorflow.contrib import learn
import numpy as np
import os
import time
import datetime
import logging
import yaml

# Project modules
import preprocessing as pp
import CNN

# Constants
# ==================================================

RUN_DIRECTORY = "runs"
SEMEVAL_FOLDER = '../data/SemEval/Subtask1'
RESTAURANT_TRAIN = os.path.join(SEMEVAL_FOLDER, 'restaurant', 'train.xml')
RESTAURANT_TEST = os.path.join(SEMEVAL_FOLDER, 'restaurant', 'test',
                               'test_gold.xml')
LAPTOP_TRAIN = os.path.join(SEMEVAL_FOLDER, 'laptop', 'train.xml')
LAPTOP_TEST = os.path.join(SEMEVAL_FOLDER, 'laptop', 'test', 'test_gold.xml')

if __name__ == '__main__':

    timestamp = str(int(time.time()))

    # Parameters
    # ==================================================

    # Directory name of current run
    tf.flags.DEFINE_string(
            "directory_name", "current",
            "Directory name of the current run where log and other information"
            " will be stored.\n" +
            "Information will be stored at: " +
            "RUN_DIRECTORY/directory_name/timestamp (default name: current)")

    # Data loading parameters
    tf.flags.DEFINE_float(
            "dev_sample_percentage", .1,
            "Percentage of the training data to use for validation")
    tf.flags.DEFINE_string(
            "positive_data_file", "../data/rt-polaritydata/rt-polarity.pos",
            "Data source for the positive data.")
    tf.flags.DEFINE_string(
            "negative_data_file", "../data/rt-polaritydata/rt-polarity.neg",
            "Data source for the negative data.")

    # Model Hyperparameters
    tf.flags.DEFINE_boolean(
            "enable_word_embeddings",
            True, "Enable/disable the word embedding (default: False)")
    tf.flags.DEFINE_integer(
            "embedding_dim", 128,
            "Dimensionality of character embedding (default: 128)")
    tf.flags.DEFINE_string(
            "filter_sizes", "3,4,5",
            "Comma-separated filter sizes (default: '3,4,5')")
    tf.flags.DEFINE_integer(
            "num_filters", 128,
            "Number of filters per filter size (default: 128)")
    tf.flags.DEFINE_float(
            "dropout_keep_prob", 0.5,
            "Dropout keep probability (default: 0.5)")
    tf.flags.DEFINE_float(
            "l2_reg_lambda", 0.0,
            "L2 regularization lambda (default: 0.0)")

    # Training parameters
    tf.flags.DEFINE_integer(
            "batch_size", 64,
            "Batch Size (default: 64)")
    tf.flags.DEFINE_integer(
            "num_epochs", 200,
            "Number of training epochs (default: 200)")
    tf.flags.DEFINE_integer(
            "evaluate_every", 100,
            "Evaluate model on dev set after this many steps (default: 100)")
    tf.flags.DEFINE_integer(
            "checkpoint_every", 100,
            "Save model after this many steps (default: 100)")
    tf.flags.DEFINE_integer(
            "num_checkpoints", 5,
            "Number of checkpoints to store (default: 5)")

    # Misc Parameters
    tf.flags.DEFINE_boolean(
            "allow_soft_placement", True,
            "Allow device soft device placement")
    tf.flags.DEFINE_boolean(
            "log_device_placement", False,
            "Log placement of ops on devices")

    FLAGS = tf.flags.FLAGS
    FLAGS._parse_flags()
    CURRENT_RUN_DIRECTORY = os.path.join(os.path.curdir, RUN_DIRECTORY,
                                         FLAGS.directory_name, timestamp)

    # Logger
    # ==================================================

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # File handler which logs even debug messages
    file_handler = logging.FileHandler('log.log')
    file_handler.setLevel(logging.DEBUG)

    # Other file handler to store information for each run
    if not os.path.exists(CURRENT_RUN_DIRECTORY):
        os.makedirs(CURRENT_RUN_DIRECTORY)
    log_directory = os.path.join(CURRENT_RUN_DIRECTORY, "train.log")
    run_file_handler = logging.FileHandler(log_directory)
    run_file_handler.setLevel(logging.DEBUG)

    # Console handler which logs info messages
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Create formatter and add it to the handlers
#    formatter = logging.Formatter('%(asctime)s -- %(name)s -- %(levelname)s\n'
#                                  '%(message)s\n')
    formatter = logging.Formatter("%(message)s")
    file_handler.setFormatter(formatter)
    run_file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(run_file_handler)
    logger.addHandler(console_handler)

    # Use parameters set in config file
    with open("config.yml", 'r') as ymlfile:
        cfg = yaml.load(ymlfile)

    dataset_name = cfg["datasets"]["default"]
    embedding_name = "NONE"
    if (FLAGS.enable_word_embeddings and
            cfg['word_embeddings']['default'] is not None):
        embedding_name = cfg['word_embeddings']['default']
        embedding_dimension =\
            cfg['word_embeddings'][embedding_name]['dimension']
    else:
        embedding_dimension = FLAGS.embedding_dim

    # ---
    # Information about current run stored
    # ---
    logger.debug(" *** Parameters *** ")
    for attr, value in sorted(FLAGS.__flags.items()):
        logger.debug("{}={}".format(attr.upper(), value))
    logger.debug("{}={}".format("CURRENT_RUN_DIRECTORY",
                 CURRENT_RUN_DIRECTORY))
    logger.debug("{}={}".format("WORD_EMBEDDING",
                 embedding_name))
    logger.debug("{}={}".format("DATASET (train)",
                 dataset_name))
    logger.debug("")

    # Data Preparation
    # ==================================================

    # Load data
    logger.info(" *** Loading data... *** ")

    datasets = None
    if dataset_name == "mrpolarity":
        datasets = pp.get_datasets_mrpolarity(
                cfg["datasets"][dataset_name]["positive_data_file"]["path"],
                cfg["datasets"][dataset_name]["negative_data_file"]["path"])
    elif dataset_name == "20newsgroup":
        datasets = pp.get_datasets_20newsgroup(
                subset="train",
                categories=cfg["datasets"][dataset_name]["categories"],
                shuffle=cfg["datasets"][dataset_name]["shuffle"],
                random_state=cfg["datasets"][dataset_name]["random_state"])
    elif dataset_name == "localdata":
        datasets = pp.get_datasets_localdata(
                container_path=cfg["datasets"][dataset_name]["container_path"],
                categories=cfg["datasets"][dataset_name]["categories"],
                shuffle=cfg["datasets"][dataset_name]["shuffle"],
                random_state=cfg["datasets"][dataset_name]["random_state"])

    x_text, y = pp.load_data_and_labels(datasets)

    # Build vocabulary
    max_document_length = max([len(x.split(" ")) for x in x_text])
    logger.debug("Max document length : %s", max_document_length)
    vocab_processor = (learn.preprocessing.VocabularyProcessor(
            max_document_length))
    x = np.array(list(vocab_processor.fit_transform(x_text)))
    logger.debug("Data (shape : %s):\n %s", x.shape, x)

    # Randomly shuffle data
    np.random.seed(10)
    shuffle_indices = np.random.permutation(np.arange(len(y)))
    x_shuffled = x[shuffle_indices]
    logger.debug("Data shuffled (shape: %s):\n %s", x_shuffled.shape,
                 x_shuffled)
    y_shuffled = y[shuffle_indices]
    logger.debug("Label shuffled (shape: %s):\n %s", y_shuffled.shape,
                 y_shuffled)

    # Split train/test set
    # TODO: This is very crude, should use cross-validation
    dev_sample_index = -1 * int(FLAGS.dev_sample_percentage * float(len(y)))
    x_train, x_dev = (x_shuffled[:dev_sample_index],
                      x_shuffled[dev_sample_index:])
    y_train, y_dev = (y_shuffled[:dev_sample_index],
                      y_shuffled[dev_sample_index:])

    logger.info("")
    logger.info(" ==> VOCABULARY <== ")
    logger.info("Vocabulary size : %s", len(vocab_processor.vocabulary_))

    # Log the first 10 words and the final one
    logger.debug("Log the first 10 words of the vocabulary and the last one")
    for i in range(0, len(vocab_processor.vocabulary_)):
        logger.debug("Word in the vocabulary : %s",
                     vocab_processor.vocabulary_.reverse(i))
        if (i == 10):
            break
    logger.debug("Last word in the vocabulary : %s",
                 vocab_processor.vocabulary_.reverse(
                         len(vocab_processor.vocabulary_) - 1))

    logger.info("Train/Dev : %s/%s", len(y_train), len(y_dev))
    logger.info("")

    # Training
    # ==================================================

    logger.info(" *** Define Graph *** ")
    with tf.Graph().as_default():
        session_conf = tf.ConfigProto(
          allow_soft_placement=FLAGS.allow_soft_placement,
          log_device_placement=FLAGS.log_device_placement)
        sess = tf.Session(config=session_conf)
        with sess.as_default():

            # Instantiate CNN & minimising the loss
            # ==================================================

            logger.info(" *** CNN *** ")

            cnn = CNN.TextCNN(
                sequence_length=x_train.shape[1],
                num_classes=y_train.shape[1],
                vocab_size=len(vocab_processor.vocabulary_),
                embedding_size=embedding_dimension,
                filter_sizes=list(map(int, FLAGS.filter_sizes.split(","))),
                num_filters=FLAGS.num_filters,
                l2_reg_lambda=FLAGS.l2_reg_lambda)

            # Define Training procedure
            global_step = tf.Variable(0, name="global_step", trainable=False)
            # TODO : Other optimizer
            optimizer = tf.train.AdamOptimizer(1e-3)
            grads_and_vars = optimizer.compute_gradients(cnn.loss)
            train_op = optimizer.apply_gradients(grads_and_vars,
                                                 global_step=global_step)

            # Keep track of gradient values and sparsity (optional)
            grad_summaries = []
            for g, v in grads_and_vars:
                if g is not None:
                    grad_hist_summary = tf.summary.histogram(
                        "{}/grad/hist".format(v.name), g)
                    sparsity_summary = tf.summary.scalar(
                        "{}/grad/sparsity".format(v.name),
                        tf.nn.zero_fraction(g))
                    grad_summaries.append(grad_hist_summary)
                    grad_summaries.append(sparsity_summary)
            grad_summaries_merged = tf.summary.merge(grad_summaries)

            # Summaries
            # ==================================================

            # Output directory for models and summaries
            out_dir = os.path.abspath(os.path.join(
                    os.path.curdir, CURRENT_RUN_DIRECTORY))
            logger.info("")
            logger.info("Writing to {}".format(out_dir))

            # Summaries for loss and accuracy
            loss_summary = tf.summary.scalar("loss", cnn.loss)
            acc_summary = tf.summary.scalar("accuracy", cnn.accuracy)

            # Train Summaries
            train_summary_op = tf.summary.merge([loss_summary, acc_summary,
                                                 grad_summaries_merged])
            train_summary_dir = os.path.join(out_dir, "summaries", "train")
            train_summary_writer = tf.summary.FileWriter(train_summary_dir,
                                                         sess.graph)

            # Dev summaries
            dev_summary_op = tf.summary.merge([loss_summary, acc_summary])
            dev_summary_dir = os.path.join(out_dir, "summaries", "dev")
            dev_summary_writer = tf.summary.FileWriter(dev_summary_dir,
                                                       sess.graph)

            # Checkpointing
            # ==================================================

            checkpoint_dir = os.path.abspath(os.path.join(out_dir,
                                                          "checkpoints"))
            checkpoint_prefix = os.path.join(checkpoint_dir, "model")

            # Tensorflow assumes this directory already exists so we
            # need to create it
            if not os.path.exists(checkpoint_dir):
                os.makedirs(checkpoint_dir)
            saver = tf.train.Saver(tf.global_variables(),
                                   max_to_keep=FLAGS.num_checkpoints)

            # Write vocabulary
            # ==================================================

            vocab_processor.save(os.path.join(out_dir, "vocab"))

            # Initializing the variables
            # ==================================================

            sess.run(tf.global_variables_initializer())

            if (FLAGS.enable_word_embeddings and
                    cfg['word_embeddings']['default'] is not None):
                vocabulary = vocab_processor.vocabulary_
                initW = None
                if embedding_name == 'word2vec':
                    # Load embedding vectors from the word2vec
                    logger.info("Load word2vec file {}".format(
                            cfg['word_embeddings']['word2vec']['path']))
                    initW = pp.load_embedding_vectors_word2vec(
                            vocabulary,
                            cfg['word_embeddings']['word2vec']['path'],
                            cfg['word_embeddings']['word2vec']['binary'])
                    logger.info("Word2vec file has been loaded")
                elif embedding_name == 'glove':
                    # Load embedding vectors from the glove
                    logger.info("Load glove file {}".format(
                            cfg['word_embeddings']['glove']['path']))
                    initW = pp.load_embedding_vectors_glove(
                            vocabulary,
                            cfg['word_embeddings']['glove']['path'],
                            embedding_dimension)
                    logger.info("Glove file has been loaded")
                sess.run(cnn.W.assign(initW))

            # Functions
            # ==================================================

            def train_step(x_batch, y_batch):
                """
                A single training step
                """

                feed_dict = {
                  cnn.input_x: x_batch,
                  cnn.input_y: y_batch,
                  cnn.dropout_keep_prob: FLAGS.dropout_keep_prob
                }
                _, step, summaries, loss, accuracy = sess.run(
                    [train_op, global_step, train_summary_op, cnn.loss,
                     cnn.accuracy],
                    feed_dict)
                time_str = datetime.datetime.now().isoformat()
                logger.info("{}: step {}, loss {:g}, acc {:g}".format(
                             time_str, step, loss, accuracy))
                train_summary_writer.add_summary(summaries, step)

            def dev_step(x_batch, y_batch, writer=None):
                """
                Evaluates model on a dev set (example: a validation step,
                the whole training set...). Disables dropout.
                """

                feed_dict = {
                  cnn.input_x: x_batch,
                  cnn.input_y: y_batch,
                  cnn.dropout_keep_prob: 1.0
                }
                step, summaries, loss, accuracy = sess.run(
                    [global_step, dev_summary_op, cnn.loss, cnn.accuracy],
                    feed_dict)
                time_str = datetime.datetime.now().isoformat()
                logger.info("{}: step {}, loss {:g}, acc {:g}".format(
                             time_str, step, loss, accuracy))
                if writer:
                    writer.add_summary(summaries, step)

            # Generate batches
            # ==================================================

            data = list(zip(x_train, y_train))
            batches = pp.batch_iter(data, FLAGS.batch_size, FLAGS.num_epochs)

            # Training loop. For each batch...
            # ==================================================

            logger.info("")
            logger.info("*** TRAINING LOOP ***")

            for batch in batches:

                x_batch, y_batch = zip(*batch)
                train_step(x_batch, y_batch)
                current_step = tf.train.global_step(sess, global_step)

                # Progress
                last_step = (pp.batch_number(
                    data,
                    FLAGS.batch_size,
                    FLAGS.num_epochs) * FLAGS.num_epochs)
                progress_pourcentage = round(current_step*100/last_step, 2)

                # Evaluation and checkpoint are made every given steps but
                # also at the last step of the algorithm
                if (current_step % FLAGS.evaluate_every == 0 or
                        progress_pourcentage == float(100)):
                    logger.info("")
                    logger.info("Evaluation :")
                    dev_step(x_dev, y_dev, writer=dev_summary_writer)
                    logger.info("")
                if (current_step % FLAGS.checkpoint_every == 0 or
                        progress_pourcentage == float(100)):
                    path = saver.save(sess, checkpoint_prefix,
                                      global_step=current_step)
                    logger.info("Saved model checkpoint to {}".format(path))
                    logger.info("")

                logging.info("Progress : {}%".format(progress_pourcentage, 2))
                logger.info("")
