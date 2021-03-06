#! /usr/bin/env python3

"""
Prediction part of the algorithm.
"""

import tensorflow as tf
import numpy as np
import os
import preprocessing as pp
import analysis as an
from tensorflow.contrib import learn
import csv
from sklearn import metrics
import pandas as pd
import matplotlib.pyplot as plt
from pandas_ml import ConfusionMatrix
import yaml
import logging

# Constants
# ============================================

SEMEVAL_FOLDER = '../data/SemEval/Subtask1'
RESTAURANT_TRAIN = os.path.join(SEMEVAL_FOLDER, 'restaurant', 'train.xml')
RESTAURANT_TEST = os.path.join(SEMEVAL_FOLDER, 'restaurant', 'test',
                               'test_gold.xml')
LAPTOP_TRAIN = os.path.join(SEMEVAL_FOLDER, 'laptop', 'train.xml')
LAPTOP_TEST = os.path.join(SEMEVAL_FOLDER, 'laptop', 'test', 'test_gold.xml')
RESTAURANT_ENTITIES = ['FOOD', 'DRINKS', 'SERVICE', 'RESTAURANT', 'AMBIENCE',
                       'LOCATION']
LAPTOP_ENTITIES = ['LAPTOP', 'HARDWARE', 'SHIPPING', 'COMPANY', 'SUPPORT',
                   'SOFTWARE']
POLARITY = ['positive', 'neutral', 'negative']
RESTAURANT_ASPECTS = [
        'RESTAURANT#GENERAL', 'RESTAURANT#PRICES', 'RESTAURANT#MISCELLANEOUS',
        'FOOD#PRICES', 'FOOD#QUALITY', 'FOOD#STYLE_OPTIONS',
        'DRINKS#PRICES', 'DRINKS#QUALITY', 'DRINKS#STYLE_OPTIONS',
        'AMBIENCE#GENERAL', 'SERVICE#GENERAL', 'LOCATION#GENERAL']

# Functions
# ==================================================


def softmax(x):
    """Compute softmax values for each sets of scores in x."""
    if x.ndim == 1:
        x = x.reshape((1, -1))
    max_x = np.max(x, axis=1).reshape((-1, 1))
    exp_x = np.exp(x - max_x)
    return exp_x / np.sum(exp_x, axis=1).reshape((-1, 1))


def prediction_process_CNN(folderpath_run, config_file, focus):
    """
    Process predictions for one CNN in order to obtain some measures about
    its efficiency.
    :param folderpath_run: The filepath of a run of train.py.
    :param config_file: The configuration file of the project opened with yaml
    library.
    :param focus: (required) 'feature' or 'polarity'. This precises the
    folder of a CNN. It will lead to the folder 'CNN_feature' or
    'CNN_polarity'.
    :type focus: string
    :return: datasets['data'], all_predictions, datasets['target_names'].
    datasets['data'] are the sentences before cleaning (after cleaning it is
    x_raw), all_predictions represents the prediction of the algorithm
    depending on the focus and datasets['target_names'] are the labels
    possible for the predictions.
    """

    datasets = None

    # Load data
    dataset_name = config_file["datasets"]["default"]
    if dataset_name == "semeval":
        current_domain = config_file["datasets"][dataset_name]["current_domain"]
        if current_domain == 'RESTAURANT':
            datasets = pp.get_dataset_semeval(RESTAURANT_TEST, focus,
                                              FLAGS.aspects)
        elif current_domain == 'LAPTOP':
            datasets = pp.get_dataset_semeval(LAPTOP_TEST, focus)
        else:
            raise ValueError("The 'current_domain' parameter in the " +
                             "'config.yml' file must be 'RESTAURANT' " +
                             "or 'LAPTOP'")

    x_raw, y_test = pp.load_data_and_labels(datasets)
    y_test = np.argmax(y_test, axis=1)
    logger.debug("Total number of test examples: {}".format(len(y_test)))

    # Map data into vocabulary
    vocab_path = os.path.join(folderpath_run, 'CNN_' + focus, 'vocab')
    vocab_processor = learn.preprocessing.VocabularyProcessor.restore(
            vocab_path)
    x_test = np.array(list(vocab_processor.transform(x_raw)))

    logger.info("")
    logger.info("Evaluation :")
    logger.info("")

    # Evaluation
    # ==================================================
    checkpoints_folder = os.path.join(folderpath_run, 'CNN_' + focus,
                                      'checkpoints')
    checkpoint_file = tf.train.latest_checkpoint(checkpoints_folder)
    graph = tf.Graph()

    with graph.as_default():

        session_conf = tf.ConfigProto(
          allow_soft_placement=FLAGS.allow_soft_placement,
          log_device_placement=FLAGS.log_device_placement)
        sess = tf.Session(config=session_conf)

        with sess.as_default():

            # Load the saved meta graph and restore variables
            saver = tf.train.import_meta_graph(
                    "{}.meta".format(checkpoint_file))
            saver.restore(sess, checkpoint_file)

            # Get the placeholders from the graph by name
            input_x = graph.get_operation_by_name("input_x").outputs[0]
            # input_y = graph.get_operation_by_name("input_y").outputs[0]
            dropout_keep_prob = graph.get_operation_by_name(
                    "dropout_keep_prob").outputs[0]

            # Tensors we want to evaluate
            scores = graph.get_operation_by_name("output/scores").outputs[0]

            # Tensors we want to evaluate
            predictions = graph.get_operation_by_name(
                    "output/predictions").outputs[0]

            # Generate batches for one epoch
            batches = pp.batch_iter(
                    list(x_test), FLAGS.batch_size, 1, shuffle=False)

            # Collect the predictions here
            all_predictions = []
            all_probabilities = None

            for x_test_batch in batches:
                batch_predictions_scores = sess.run(
                        [predictions, scores],
                        {input_x: x_test_batch, dropout_keep_prob: 1.0})
                all_predictions = np.concatenate(
                        [all_predictions, batch_predictions_scores[0]])
                probabilities = softmax(batch_predictions_scores[1])
                if all_probabilities is not None:
                    all_probabilities = np.concatenate(
                            [all_probabilities, probabilities])
                else:
                    all_probabilities = probabilities

    # Print accuracy if y_test is defined
    if y_test is not None:
        correct_predictions = float(sum(all_predictions == y_test))
        logger.debug("Total number of test examples: {}".format(len(y_test)))
        logger.info("")
        logger.info(
                "Accuracy: {:g}".format(
                        correct_predictions/float(len(y_test))))

        class_report = metrics.classification_report(
                y_test, all_predictions,
                target_names=datasets['target_names'])
        logger.info(class_report)

        confusion_matrix = ConfusionMatrix(y_test, all_predictions)
        logger.info(confusion_matrix)
        logger.info("")
        str_labels = "Labels : "
        for idx, label in enumerate(datasets['target_names']):
            str_labels += "{} = {}, ".format(idx, label)
        logger.info(str_labels)
        logger.info("")

    # Save the evaluation to a csv
    predictions_human_readable = np.column_stack(
            (np.array(x_raw),
             [int(prediction) for prediction in all_predictions],
             ["{}".format(probability) for probability in all_probabilities]))
    out_path = os.path.join(checkpoints_folder, "..", "prediction.csv")

    logger.info("Saving evaluation to {0}".format(out_path))

    with open(out_path, 'w') as f:
        csv.writer(f).writerows(predictions_human_readable)

    return (datasets['data'], all_predictions, datasets['target_names'],
            class_report)

if __name__ == '__main__':

    with open("config.yml", 'r') as ymlfile:
        cfg = yaml.load(ymlfile)

    # Parameters
    # ==================================================

    # Data Parameters

    # Eval Parameters
    tf.flags.DEFINE_integer("batch_size", 64, "Batch Size (default: 64)")
    tf.flags.DEFINE_string("checkpoint_dir", "",
                           "Checkpoint directory from training run")

    # Misc Parameters
    tf.flags.DEFINE_boolean("allow_soft_placement", True,
                            "Allow device soft device placement")
    tf.flags.DEFINE_boolean("log_device_placement", False,
                            "Log placement of ops on devices")
    tf.flags.DEFINE_boolean("aspects",
                            False,
                            "Scope widened to aspects and not only entities")

    # Precise if predictions is on features or polarity
    tf.flags.DEFINE_string("focus", "", "'feature' or 'polarity'")

    FLAGS = tf.flags.FLAGS
    FLAGS._parse_flags()

    # Logger
    # ==================================================

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # File handler which logs even debug messages
    file_handler = logging.FileHandler('log.log')
    file_handler.setLevel(logging.DEBUG)

    # Other file handler to store information for each run
    log_directory = os.path.join(FLAGS.checkpoint_dir, "eval.log")
    run_file_handler = logging.FileHandler(log_directory)
    run_file_handler.setLevel(logging.DEBUG)

    # Console handler which logs info messages
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Create formatter and add it to the handlers
    formatter = logging.Formatter("%(message)s")
    file_handler.setFormatter(formatter)
    run_file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(run_file_handler)
    logger.addHandler(console_handler)
    logger.debug(" *** Parameters *** ")
    for attr, value in sorted(FLAGS.__flags.items()):
        logger.debug("{}={}".format(attr.upper(), value))
    logger.debug("")

    # ----------
    # Prediction part :
    # ----------
    # First, construction of the representation of the XML document which we
    # want to predict --> Pandas.dataframe
    # Then, prediction of the outputs of both CNN_feature and CNN_polarity to
    # evaluate the accuracy of each CNN.
    # Afterwards, construction of the whole predictions.
    # Then, compute the accuracy, recall and f-score  to observ if the whole
    # model is good or not.
    # Finally, print the predicted and actual results in a CSV file.
    # ==================================================

    # ==================================================
    # Dataframe for actual and whole results
    # dataframe_actual = 'review_id', 'sentence_id', 'text', 'feature',
    #                    'polarity'
    # whole_prediction = 'review_id', 'sentence_id', 'text', 'feature',
    #                    'pred_feature', 'polarity', 'pred_polarity'
    # ==================================================

    dataset_name = cfg["datasets"]["default"]
    current_domain = cfg["datasets"][dataset_name]["current_domain"]
    if current_domain == 'RESTAURANT':
        dataframe_actual = pp.parse_XML(RESTAURANT_TEST, FLAGS.aspects)
        dataframe_actual = pp.select_and_simplify_dataset(
                dataframe_actual, RESTAURANT_TEST, FLAGS.aspects)
    elif current_domain == 'LAPTOP':
        dataframe_actual = pp.parse_XML(LAPTOP_TEST)
        dataframe_actual = pp.select_and_simplify_dataset(
                dataframe_actual, LAPTOP_TEST)
    else:
        raise ValueError("The 'current_domain' parameter in the " +
                         "'config.yml' file must be 'RESTAURANT' " +
                         "or 'LAPTOP'")

    whole_prediction = pd.DataFrame(data=None, columns=[
            'review_id', 'sentence_id', 'text', 'feature', 'pred_feature',
            'polarity', 'pred_polarity'])

    # ==================================================
    # CNN_feature predictions
    # ==================================================

    sentences_feature, all_predictions_feature, target_names_feature, feature_class_report =\
        prediction_process_CNN(FLAGS.checkpoint_dir, cfg, 'feature')

    # ==================================================
    # CNN_polarity predictions
    # ==================================================

    sentences_polarity, all_predictions_polarity, target_names_polarity, polarity_class_report =\
        prediction_process_CNN(FLAGS.checkpoint_dir, cfg, 'polarity')

    # ==================================================
    # Construction of the whole predictions
    # ==================================================
    for index, row in dataframe_actual.iterrows():
        review_id = row['review_id']
        sentence_id = row['sentence_id']
        text = row['text']
        feature = row['feature']
        polarity = row['polarity']

        # Feature
        # ==================================================

        # Retrieve index in the list of sentences
        index_text = sentences_feature.index(text)

        # Search the feature which corresponds to the text (retrieve the first
        # occurence)
        pred_feature = all_predictions_feature[index_text]

        # Translate to corresponding label
        pred_feature = target_names_feature[int(pred_feature)]

        # Polarity
        # ==================================================

        # Retrieve index in the list of sentences
        index_text = sentences_polarity.index(text)

        # Search the feature which corresponds to the text (retrieve the first
        # occurence)
        pred_polarity = all_predictions_polarity[index_text]

        # Translate to corresponding label
        pred_polarity = target_names_polarity[int(pred_polarity)]

        whole_prediction = whole_prediction.append(
                pd.DataFrame({'review_id': review_id,
                              'sentence_id': sentence_id,
                              'text': text,
                              'feature': feature,
                              'pred_feature': pred_feature,
                              'polarity': polarity,
                              'pred_polarity': pred_polarity},
                             index=[0]), ignore_index=True)

    # Add a column to check if the whole prediction is correct (feature and
    # pred_feature must be equal AND polarity and pred_polarity must also be
    # equal)
    whole_prediction['check'] =\
        ((whole_prediction.feature == whole_prediction.pred_feature) &
         (whole_prediction.polarity == whole_prediction.pred_polarity))

    # ==================================================
    # Effectiveness of the algorithm
    # ==================================================

    # Construction of dictionary to store new classes
    # Ex : FOOD, positive will be 0, FOOD, neutral : 1...etc...
    dict_polarity = {}
    for key, value in zip(POLARITY, list(range(len(POLARITY)))):
        dict_polarity[key] = value

    dict_entity_polarity = {}
    if current_domain == 'RESTAURANT':
        if not FLAGS.aspects:
            index = 0
            for entity in RESTAURANT_ENTITIES:
                dict_polarity = {}
                for polarity in POLARITY:
                    dict_polarity[polarity] = index
                    index += 1
                dict_entity_polarity[entity] = dict_polarity
        else:
            index = 0
            for entity in RESTAURANT_ASPECTS:
                dict_polarity = {}
                for polarity in POLARITY:
                    dict_polarity[polarity] = index
                    index += 1
                dict_entity_polarity[entity] = dict_polarity
    elif current_domain == 'LAPTOP':
        index = 0
        for entity in LAPTOP_ENTITIES:
            dict_polarity = {}
            for polarity in POLARITY:
                dict_polarity[polarity] = index
                index += 1
            dict_entity_polarity[entity] = dict_polarity
    else:
        raise ValueError("The 'current_domain' parameter in the " +
                         "'config.yml' file must be 'RESTAURANT' " +
                         "or 'LAPTOP'")

    # Create a new DataFrame to add to whole_prediction. The new DataFrame is
    # composed of 'new_class' and 'pred_new_class' columns
    list_of_rows = []
    for index, row in whole_prediction.iterrows():
        list_of_rows.append(
                [dict_entity_polarity[row['feature']][row['polarity']],
                 dict_entity_polarity[row['pred_feature']][row['pred_polarity']]])
    df_to_append = pd.DataFrame(data=list_of_rows,
                                columns=['new_class', 'pred_new_class'])
    whole_prediction = whole_prediction.assign(
             new_class=df_to_append['new_class'])
    whole_prediction = whole_prediction.assign(
             pred_new_class=df_to_append['pred_new_class'])

    logger.info("Effectiveness of the whole algorithm")
    logger.info("")
    class_report = metrics.classification_report(
            whole_prediction['new_class'],
            whole_prediction['pred_new_class'])
    logger.info(class_report)

    logger.info("")
    for entity, dict_polarity in dict_entity_polarity.items():
        for polarity, num_class in dict_polarity.items():
            logger.info("{} : {} - {}".format(num_class, entity, polarity))

    # Save the predictions into a CSV file inside the folder of the current run
    path_prediction_file = os.path.join(FLAGS.checkpoint_dir,
                                        'predictions.csv')
    whole_prediction.to_csv(path_prediction_file, encoding='utf-8',
                            columns=['review_id', 'sentence_id', 'text',
                                     'feature', 'pred_feature',
                                     'polarity', 'pred_polarity',
                                     'check', 'new_class', 'pred_new_class'])

    # ==================================================
    # Display charts
    # ==================================================
    an.bar_chart_classification_report(feature_class_report,
                                       "Effectiveness of CNN_feature",
                                       FLAGS.checkpoint_dir)
    an.bar_chart_classification_report(polarity_class_report,
                                       "Effectiveness of CNN_polarity",
                                       FLAGS.checkpoint_dir)
    an.bar_chart_classification_report(class_report,
                                       "Effectiveness of whole algorithm",
                                       FLAGS.checkpoint_dir)

    an.pie_chart_support_distribution(feature_class_report,
                                      "Data distribution for CNN_feature",
                                      FLAGS.checkpoint_dir)
    an.pie_chart_support_distribution(polarity_class_report,
                                      "Data distribution for CNN_polarity",
                                      FLAGS.checkpoint_dir)
    an.pie_chart_support_distribution(class_report,
                                      "Data distribution for whole algorithm",
                                      FLAGS.checkpoint_dir)
