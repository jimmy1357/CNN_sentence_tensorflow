# -*- coding: utf-8 -*-
import cPickle
import numpy as np
from collections import defaultdict, OrderedDict
import re
import warnings
import sys
import time
import numpy as np
import os
import time
import datetime
warnings.filterwarnings("ignore") 
import tensorflow as tf
from tensorflow.contrib import learn
"""
使用tensorflow构建CNN模型进行文本分类
"""
vector_size = 100;
sentence_length = 100;
hidden_layer_input_size = 100
filter_hs=[3,4,5]
num_filters = 128
img_h = sentence_length
img_w = vector_size
filter_w = img_w
batch_size=100
word_idx_map_size = 75924#18766#75924

#一些数据预处理的方法====================================== 
#####################################################################################
# 将评论句子向量化：向量中的值是词在index map中的index，每个句子向量为max_l维
# 将输入的句子中的词，获取其在word_idx_map中的index，当词数不足max_l时，补充0.
#
#####################################################################################
def get_idx_from_sent(sent, word_idx_map, max_l):
    """
    Transforms sentence into a list of indices. Pad with zeroes.
    """
    x = []
    words = sent.split()
    for word in words:
        if word in word_idx_map:
            x.append(word_idx_map[word])
    while len(x) < max_l:
        x.append(0)
    #一个训练的一个输入 形式为[0,0,0,0,x11,x12,,,,0,0,0] 向量长度为max_l+2*filter_h-2
    #print x
    return x 

# generates a batch of training corpus, vectorizes this batch of sentences and corresponding labels
# eg. sentence: 这个 手机 真 不错 ---> [23, 14, 566, 45, 0, 0, ......, 0]
#     label: 正向情感             ---> [0, 1]
def generate_batch(minibatch_index):
    minibatch_data = revs[minibatch_index*batch_size:(minibatch_index+1)*batch_size]
    batchs = np.ndarray(shape=(batch_size, sentence_length), dtype=np.float32)
    labels = np.ndarray(shape=(batch_size, 2), dtype=np.float32)
    
    for i in range(batch_size):
        sentece = minibatch_data[i]["text"]
        lable =  minibatch_data[i]["y"]
        if lable==1:
            labels[i] = [0,1]# 无序分类，因此分两类就是2维的
        else:
            labels[i] = [1,0]#
        batch = get_idx_from_sent(sentece, word_idx_map, sentence_length)
        batchs[i] = batch
    return batchs, labels

def get_test_batch(cv=1): # process_data.py中设定的cv最大值为10，因此随机出的cv值为1 的概率为10%，因此这里的意思就是随机取10%的数据作为测试集
    test = []
    for rev in revs:
        if rev["split"]==cv:
            test.append(rev)        
    minibatch_data = test
    test_size =len(minibatch_data)
    batchs = np.ndarray(shape=(test_size, sentence_length), dtype=np.float32)
    labels = np.ndarray(shape=(test_size, 2), dtype=np.float32)  
    for i in range(test_size):
        sentece = minibatch_data[i]["text"]
        lable =  minibatch_data[i]["y"]
        if lable==1:
            labels[i] = [0,1]
        else:
            labels[i] = [1,0]
        batch = get_idx_from_sent(sentece, word_idx_map, sentence_length)
        batchs[i] = batch
    return batchs, labels

print "loading data...",
x = cPickle.load(open("mr.p","rb"))
# 读取出预处理后的数据 revs {"y":label,"text":"word1 word2 ..."}
#                          word_idx_map["word"]==>index
#                        vocab["word"]==>frequency
revs, _, _, word_idx_map, vocab = x[0], x[1], x[2], x[3], x[4] 
print "data loaded!"
revs = np.random.permutation(revs) #原始的sample正负样本是分别聚在一起的，这里随机打散
n_batches = len(revs)/batch_size#
n_train_batches = int(np.round(n_batches*0.9))

def weight_variable(shape):
    initial = tf.truncated_normal(shape, stddev=0.1)
    return tf.Variable(initial)
#产生常量矩阵
def bias_variable(shape):
    initial = tf.constant(0.1, shape=shape)
    return tf.Variable(initial)

#卷积图层 第一个卷积
# strides：每跨多少步抽取信息，strides[1, x_movement,y_movement, 1]， [0]和strides[3]必须为1
# padding：边距处理，“SAME”表示输出图层和输入图层大小保持不变，设置为“ VALID ”时表示舍弃多余边距(丢失信息)
# 不同的卷积层，对应了不同的池化层，保证池化后的数据可以直接在深度上concat(串联)
def conv2d(x, W):
    return tf.nn.conv2d(x, W, strides=[1, 1, 1, 1], padding='VALID')
# 定义pooling图层
# pooling：解决跨步大时可能丢失一些信息的问题,max-pooling就是在前图层上依次不重合采样(img_h-filter_h+1) * 1 的窗口最大值
def max_pool_2x2(x, filter_h):
    return tf.nn.max_pool(x, ksize=[1, img_h-filter_h+1, 1, 1],strides=[1, 1, 1, 1], padding='VALID')
#开始定义模型============================================
#sess = tf.InteractiveSession()  --jichen
config = tf.ConfigProto(allow_soft_placement=True,  log_device_placement=True)
with tf.Session(config=config) as sess:
     
    #占位符 真实的输入输出
    x_in = tf.placeholder(tf.int32, shape=[None,sentence_length],name="input_x")
    #y_in = tf.placeholder("float", [None,2],name="input_y")#2分类问题
    y_in = tf.placeholder(tf.float32, [None,2],name="input_y")#2分类问题

    # Embedding layer===============================
    #随机初始化Word2vec向量矩阵，这个矩阵也是要学习的词向量矩阵
    embeddings = tf.Variable(tf.random_uniform([word_idx_map_size, vector_size], -1.0, 1.0))
    #将输入的一批 原始 词下标 向量，转换为对应的word2vec向量矩阵，作为整个网络的输入
    x_image_tmp = tf.nn.embedding_lookup(embeddings, x_in) # 按照x_in顺序，返回embeddings中的第x_in行
    #输入size: sentence_length*vector_size
    #x_image = tf.reshape(x_image_tmp, [-1,sentence_length,vector_size,1])======>>>>>
    #将[None, sequence_length, embedding_size]转为[None, sequence_length, embedding_size, 1]
    x_image = tf.expand_dims(x_image_tmp, -1)#单通道 (函数本身是在最后一维后再添加一维，默认值为1)

    # 定义卷积层===================================
    # 从filter_hs的定义看来，一共三种卷积核，大小分别为3*100, 4*100, 5*100
    # 这里仿照inception-v3的网络结构，将三种不同的卷积层分别训练，然后用concat函数在深度一维联结起来
    W_conv = []
    b_conv = []
    for filter_h in filter_hs:
        #卷积的patch大小：vector_size*filter_h, 通道数量：1, 卷积数量：hidden_layer_input_size
        filter_shape = [filter_h, vector_size, 1, num_filters]
        W_conv1 = tf.Variable(tf.truncated_normal(filter_shape, stddev=0.1), name="W")
        b_conv1 = tf.Variable(tf.constant(0.1, shape=[num_filters]), name="b")
        #W_conv1 = weight_variable([filter_h, vector_size, 1, hidden_layer_input_size])
        W_conv.append(W_conv1)
        #b_conv1 = bias_variable([hidden_layer_input_size])
        b_conv.append(b_conv1)

    #进行卷积操作
    # 同时构建三个卷积层，输入均为 原始句子向量矩阵
    h_conv = []
    for W_conv1,b_conv1 in zip(W_conv,b_conv):
        h_conv1 = tf.nn.relu(conv2d(x_image, W_conv1) + b_conv1) #输出size: (sentence_length-filter_h+1,1)
        h_conv.append(h_conv1)

    #pool层========================================
    # 同时构建三个池化层，输入分别为上述三个卷积层的输出
    h_pool_output = []
    for h_conv1,filter_h in zip(h_conv,filter_hs):
        h_pool1 = max_pool_2x2(h_conv1, filter_h) #输出size:1
        h_pool_output.append(h_pool1)
        

    #全连接层=========================================
    l2_reg_lambda=0.001
    #输入reshape
    num_filters_total = num_filters * len(filter_hs)
    h_pool = tf.concat(h_pool_output, 3) # 将h_pool_output在卷积层深度一维进行联结
    h_pool_flat = tf.reshape(h_pool, [-1, num_filters_total]) # flatten
    #h_pool_flat = tf.reshape(h_pool, [-1, hidden_layer_input_size*len(filter_hs)])

    keep_prob = tf.placeholder("float")
    h_drop = tf.nn.dropout(h_pool_flat, keep_prob)
    #W = tf.Variable(tf.random_uniform([num_filters_total, 2], -1.0, 1.0))
    # 构建最后一层，进行分类
    W = tf.Variable(tf.truncated_normal([num_filters_total, 2], stddev=0.1))
    b = tf.Variable(tf.constant(0.1, shape=[2]), name="b")
    l2_loss = tf.nn.l2_loss(W)
    l2_loss += tf.nn.l2_loss(b)

    #scores=tf.nn.softmax(tf.matmul(h_drop, W) + b) #a softmax function to convert raw scores into normalized probabilities
    scores = tf.nn.xw_plus_b(h_drop, W, b, name="scores") # wx+b

    # 使用预测结果计算损失
    predictions = tf.argmax(scores, 1, name="predictions")
    losses = tf.nn.softmax_cross_entropy_with_logits(logits=scores, labels=y_in) # api changed
    loss = tf.reduce_mean(losses) + l2_reg_lambda * l2_loss
    
    # 使用预测结果计算准确率
    correct_prediction = tf.equal(tf.argmax(scores,1), tf.argmax(y_in,1))
    accuracy = tf.reduce_mean(tf.cast(correct_prediction, "float"))

    #train-modle========================================
    num_steps = 4000
    #L2正则化参数
    beta=0.001
    global_step = tf.Variable(0) 

    # 每num_steps步，更新一次学习速率
    learning_rate = tf.train.exponential_decay(1e-4, global_step, num_steps, 0.99, staircase=True)#学习率递减

    train_step = tf.train.AdagradOptimizer(learning_rate).minimize(loss,  global_step=global_step)

    #summaries,====================
    timestamp = str(int(time.time()))
    out_dir = os.path.abspath(os.path.join(os.path.curdir, "runs", timestamp))
    print("Writing to {}\n".format(out_dir))
    #loss_summary = tf.scalar_summary("loss", loss)
    #acc_summary = tf.scalar_summary("accuracy", accuracy)
    loss_summary = tf.summary.scalar("loss", loss) # api changed
    acc_summary = tf.summary.scalar("accuracy", accuracy)
    #train_summary_op = tf.merge_summary([loss_summary, acc_summary])
    train_summary_op = tf.summary.merge([loss_summary, acc_summary]) # api changed
    train_summary_dir = os.path.join(out_dir, "summaries", "train")
    #train_summary_writer = tf.train.SummaryWriter(train_summary_dir, sess.graph)
    train_summary_writer = tf.summary.FileWriter(train_summary_dir, sess.graph) # api changed
    checkpoint_dir = os.path.abspath(os.path.join(out_dir, "checkpoints"))
    checkpoint_prefix = os.path.join(checkpoint_dir, "model")
    if not os.path.exists(checkpoint_dir):
        os.makedirs(checkpoint_dir)
    saver = tf.train.Saver(tf.all_variables())  #包括embedding


    #sess.run(tf.initialize_all_variables())
    tf.global_variables_initializer().run()
    ckpt = tf.train.get_checkpoint_state("/home/nubia/jichen/workspace/classifier/CNN_sentence_tensorflow/runs/1502190431/checkpoints")  
    if ckpt and ckpt.model_checkpoint_path:
        saver.restore(sess, ckpt.model_checkpoint_path) 

    batch_x_test, batch_y_test = get_test_batch()
    current_step = tf.train.global_step(sess, global_step)
    print "current_step:", current_step
    if num_steps>int(current_step/135):
        num_steps = num_steps - int(current_step/135)
        print "continute step:",num_steps 
    else:
        num_steps = 0
    for i in range(num_steps):
        for minibatch_index in np.random.permutation(range(n_train_batches)): #随机打散 每次输入的样本的顺序都不一样
            batch_x, batch_y = generate_batch(minibatch_index)
            #train_step.run(feed_dict={x_in: batch_x, y_in: batch_y, keep_prob: 0.5})
            feed_dict={x_in: batch_x, y_in: batch_y, keep_prob: 0.5}
            _, step, summaries = sess.run([train_step, global_step, train_summary_op],feed_dict)
            train_summary_writer.add_summary(summaries, step)
        #print batch_x[0]
        #print batch_y[0]
        train_accuracy = accuracy.eval(feed_dict={x_in:batch_x_test, y_in: batch_y_test, keep_prob: 1.0})
        current_step = tf.train.global_step(sess, global_step)
        print "step %d, training accuracy %g"%(current_step, train_accuracy)
        path = saver.save(sess, checkpoint_prefix, global_step=current_step) # 持久化模型
        print("Saved model checkpoint to {}\n".format(path)) 

    """
    # 使用训练好的模型进行预测
    saver = tf.train.Saver()
    with tf.Session() as sess: 
        saver.restore(sess, '/root/alexnet.tfmodel')
        sess.run(....)
    """   
    # 疑问：embedding是什么时候更新的？训练好的模型怎么使用？ 参考word2vec的实现方法 
    norm = tf.sqrt(tf.reduce_sum(tf.square(embeddings), 1, keep_dims=True))
    normalized_embeddings = embeddings / norm
    final_embeddings = normalized_embeddings.eval()
    filename = "CNN_result_final_embeddings"
    cPickle.dump(final_embeddings, open(filename, "wb"))
    """
    #可视化  
    from matplotlib import pylab
    from sklearn.manifold import TSNE

    num_points = 400
    tsne = TSNE(perplexity=30, n_components=2, init='pca', n_iter=5000)
    two_d_embeddings = tsne.fit_transform(final_embeddings[1:num_points + 1, :])

    def plot(embeddings, labels):
        assert embeddings.shape[0] >= len(labels), 'More labels than embeddings'
        pylab.figure(figsize=(15, 15))  # in inches
        for i, label in enumerate(labels):
            x, y = embeddings[i, :]
            pylab.scatter(x, y)
            pylab.annotate(label, xy=(x, y), xytext=(5, 2), textcoords='offset points',
                           ha='right', va='bottom')
        pylab.show()


    words = [reverse_dictionary[i] for i in range(1, num_points + 1)]
    plot(two_d_embeddings, words)   
    """   
