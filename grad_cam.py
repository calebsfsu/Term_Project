# -*- coding: utf-8 -*-
"""Grad-CAM.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1QwICCweet1usv6VtaQvAU_H5v8Aw6enG
"""

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.models import Model
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Flatten, Conv3D, MaxPooling3D, GlobalAveragePooling2D
from tensorflow.keras.utils import to_categorical
from tensorflow.keras import layers
from sklearn.neighbors import NearestNeighbors
import h5py
import numpy as np
from IPython.display import Image, display
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import math
from tensorflow.keras.preprocessing import image

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from keras import backend as K

# from keras.utils import generic_utils
from google.colab.patches import cv2_imshow
import glob
import os

import matplotlib.colors as colors

from google.colab import drive
drive.mount('/content/drive')

class MidpointNormalize(colors.Normalize):
    """
    Normalise the colorbar so that diverging bars work there way either side from a prescribed midpoint value)

    e.g. im=ax1.imshow(array, norm=MidpointNormalize(midpoint=0.,vmin=-100, vmax=100))
    """
    def __init__(self, vmin=None, vmax=None, midpoint=None, clip=False):
        self.midpoint = midpoint
        colors.Normalize.__init__(self, vmin, vmax, clip)

    def __call__(self, value, clip=None):
        #I'm ignoring masked values and all kinds of edge cases to make a
        # simple example...
        x, y = [self.vmin, self.midpoint, self.vmax], [0, 0.5, 1]
        return np.ma.masked_array(np.interp(value, x, y), np.isnan(value))

def shiftedColorMap(cmap, start=0, midpoint=0.5, stop=1.0, name='shiftedcmap'):
    '''
    Function to in offset the "center" of a colormap. Useful for
    data with a negative min and positive max and you want the
    middle of the colormap's dynamic range to be at zero.

    Input
    -----
      cmap : The matplotlib colormap to be altered
      start : Offset from lowest point in the colormap's range.
          Defaults to 0.0 (no lower offset). Should be between
          0.0 and `midpoint`.
      midpoint : The new center of the colormap. Defaults to
          0.5 (no shift). Should be between 0.0 and 1.0. In
          general, this should be  1 - vmax / (vmax + abs(vmin))
          For example if your data range from -15.0 to +5.0 and
          you want the center of the colormap at 0.0, `midpoint`
          should be set to  1 - 5/(5 + 15)) or 0.75
      stop : Offset from highest point in the colormap's range.
          Defaults to 1.0 (no upper offset). Should be between
          `midpoint` and 1.0.
    '''
    cdict = {
        'red': [],
        'green': [],
        'blue': [],
        'alpha': []
    }

    # regular index to compute the colors
    reg_index = np.linspace(start, stop, 257)

    # shifted index to match the data
    shift_index = np.hstack([
        np.linspace(0.0, midpoint, 128, endpoint=False),
        np.linspace(midpoint, 1.0, 129, endpoint=True)
    ])

    for ri, si in zip(reg_index, shift_index):
        r, g, b, a = cmap(ri)

        cdict['red'].append((si, r, r))
        cdict['green'].append((si, g, g))
        cdict['blue'].append((si, b, b))
        cdict['alpha'].append((si, a, a))

    newcmap = matplotlib.colors.LinearSegmentedColormap(name, cdict)
    plt.register_cmap(cmap=newcmap)

    return newcmap

def get_data_test(all_data_paths, mode='train'):

  while True:
    for path in all_data_paths:
      try:
        data = np.load(path)
        U = data[0]
        V = data[1]
        mag=(U**2 + V**2)**(0.5)
        # U[U>0] = -0.02
        # V[V>0] = -0.02
        data = np.stack([mag])
        data = np.swapaxes(data, 0, 2)
        data = np.expand_dims(data, 0)

        k = os.path.split(path)
        out = k[0].split("/")

        yield data, path
      except Exception as e:
        print(e)
        continue

initializer = tf.keras.initializers.RandomNormal(mean=0.0, stddev=1.0, seed=1234)

# Method that sets up pre-trained models and returns layers of neural networks based on parameter 'name'

def get_model(name):
  # CNN
  if name == 'cnn':

    # Single channel input grey scale
    input_cube = keras.Input(shape = (64,64,1))

    x = layers.Conv2D(512, (3,3), activation=None, padding='same', kernel_initializer=initializer)(input_cube)
    x = layers.Activation('relu')(x)
    x = layers.BatchNormalization()(x)
    x = layers.MaxPooling2D((2,2), padding='same')(x)
    x = layers.Conv2D(256, (3,3), activation=None, padding='same',kernel_initializer=initializer)(x)
    x = layers.Activation('relu')(x)
    x = layers.BatchNormalization()(x)
    x = layers.MaxPooling2D((2,2), padding='same')(x)
    x = layers.Conv2D(128, (3,3), activation=None, padding='same',kernel_initializer=initializer)(x)
    x = layers.Activation('relu')(x)
    x = layers.BatchNormalization()(x)
    x = layers.MaxPooling2D((2,2), padding='same')(x)

    x = layers.Flatten()(x)

    x = layers.Dense(1024, activation='relu',kernel_initializer=initializer)(x)
    x = layers.Dropout(0.2, seed=1234)(x)
    x = layers.Dense(512, activation='relu',kernel_initializer=initializer)(x)
    x = layers.Dropout(0.2, seed=1234)(x)
    output = layers.Dense(3, activation='softmax',kernel_initializer=initializer)(x)

    model = keras.Model(input_cube, output)

    model.compile(optimizer='adam', loss=tf.keras.losses.CategoricalCrossentropy(
        reduction=tf.keras.losses.Reduction.SUM),metrics=['accuracy'])

    return model

  elif name == 'resnet':
    # ResNet

        # input layer takes single channel
        input_cube = keras.Input(shape=(64, 64, 1))
        # this layer converts the input from a single channel to three channels
        #   reason being ResNet expects three-channel input (RGB)
        x = layers.Conv2D(3, (3, 3), padding='same')(input_cube)
        r_model = tf.keras.applications.ResNet101(include_top=False, weights=None, input_shape=(64, 64, 3))


        x = r_model(x)
        x = layers.Flatten()(x)
        output = layers.Dense(3, activation='softmax', kernel_initializer=initializer)(x)

        model = tf.keras.Model(inputs=input_cube, outputs=output)
        opt = keras.optimizers.Adam(learning_rate=0.001)
        model.compile(optimizer=opt, loss='sparse_categorical_crossentropy', metrics=['accuracy'])

        return model
  elif name == "u_net":
    #input_size = (64,64,2)
    input_cube = keras.Input(shape=(64, 64, 1))
    conv1 = keras.layers.Conv2D(64, 3, activation = 'relu', padding = 'same')(input_cube)
    conv1 = keras.layers.Conv2D(64, 3, activation = 'relu', padding = 'same')(conv1)
    drop1 = keras.layers.Dropout(0.01)(conv1)
    pool1 = keras.layers.MaxPooling2D(pool_size=(2, 2))(drop1)

    conv2 = keras.layers.Conv2D(128, 3, activation = 'relu', padding = 'same')(pool1)
    conv2 = keras.layers.Conv2D(128, 3, activation = 'relu', padding = 'same')(conv2)
    drop2 = keras.layers.Dropout(0.01)(conv2)
    pool2 = keras.layers.MaxPooling2D(pool_size=(2, 2))(drop2)

    conv3 = keras.layers.Conv2D(256, 3, activation = 'relu', padding = 'same')(pool2)
    conv3 = keras.layers.Conv2D(256, 3, activation = 'relu', padding = 'same')(conv3)
    # pool3 = MaxPooling2D(pool_size=(2, 2))(conv3)
    # conv4 = Conv2D(512, 3, activation = 'relu', padding = 'same')(pool3)
    # conv4 = Conv2D(512, 3, activation = 'relu', padding = 'same')(conv4)

    drop3 = keras.layers.Dropout(0.01)(conv3)
    pool3 = keras.layers.MaxPooling2D(pool_size=(2, 2))(drop3)

    conv4 = keras.layers.Conv2D(512, 3, activation = 'relu', padding = 'same')(pool3)
    conv4 = keras.layers.Conv2D(512, 3, activation = 'relu', padding = 'same')(conv4)
    #drop4 = Dropout(0.01)(conv4)
    #pool4 = MaxPooling2D(pool_size=(2, 2))(drop4)
    # up6 = Conv2D(512, 2, activation = 'relu', padding = 'same')(UpSampling2D(size = (2,2))(drop5))
    # merge6 = concatenate([drop4,up6], axis = 3)
    # conv6 = Conv2D(512, 3, activation = 'relu', padding = 'same')(merge6)
    # conv6 = Conv2D(512, 3, activation = 'relu', padding = 'same')(conv6)

    up7 = keras.layers.Conv2D(256, 2, activation = 'relu', padding = 'same')(keras.layers.UpSampling2D(size = (2,2))(conv4))
    merge7 = keras.layers.concatenate([conv3,up7], axis = 3)
    drop7 = keras.layers.Dropout(0.01)(merge7)
    conv7 = keras.layers.Conv2D(256, 3, activation = 'relu', padding = 'same')(drop7)
    conv7 = keras.layers.Conv2D(256, 3, activation = 'relu', padding = 'same')(conv7)

    #pool7 = MaxPooling2D(pool_size=(2, 2))(drop3)

    up8 = keras.layers.Conv2D(128, 2, activation = 'relu', padding = 'same')(keras.layers.UpSampling2D(size = (2,2))(drop7))
    merge8 = keras.layers.concatenate([conv2,up8], axis = 3)
    drop8 = keras.layers.Dropout(0.01)(merge8)
    conv8 = keras.layers.Conv2D(128, 3, activation = 'relu', padding = 'same')(drop8)
    conv8 = keras.layers.Conv2D(128, 3, activation = 'relu', padding = 'same')(conv8)

    up9 = keras.layers.Conv2D(64, 2, activation = 'relu', padding = 'same')(keras.layers.UpSampling2D(size = (2,2))(drop8))
    merge9 = keras.layers.concatenate([conv1,up9], axis = 3)
    drop9 = keras.layers.Dropout(0.01)(merge9)
    conv9 = keras.layers.Conv2D(64, 3, activation = 'relu', padding = 'same')(drop9)
    conv9 = keras.layers.Conv2D(64, 3, activation = 'relu', padding = 'same')(conv9)

    #conv9 = Conv2D(2, 3, activation = 'relu', padding = 'same')(conv9)
    #drop9 = Dropout(0.01)(conv9)

    conv10 = keras.layers.Conv2D(1, 1, activation = 'sigmoid')(conv9)

    flat_output = keras.layers.Flatten()(conv10)
    dense_output = keras.layers.Dense(3, activation='softmax')(flat_output)


    model = keras.Model(inputs = input_cube, outputs = dense_output)
    opt = keras.optimizers.Adam(learning_rate=0.001)
    model.compile(optimizer = opt, loss = 'binary_crossentropy', metrics = ['accuracy'])
    #model.compile(optimizer = opt, loss = dice_coef_loss, metrics = ['accuracy'])
    #model.compile(optimizer = opt, loss = dice_loss, metrics = ['accuracy'])

    # model.compile(optimizer = opt, loss = u_net_loss, metrics = ['accuracy'])

    #model.compile(optimizer=opt, loss=tversky_loss, metrics=['accuracy'])
    #model.compile(optimmizer=opt, metrics=[tf.keras.metrics.MeanIoU(num_classes=2)]))
    #model.summary()
    return model

classifier_1 = get_model('cnn')
classifier_2 = get_model('resnet')
classifier_3 = get_model('u_net')

classifier_1.summary()
classifier_2.summary()
classifier_3.summary()

# Instead of hardcoding in the specific name of the last layer, we identify the
#   last layer based on it's layer type (Conv2D). This ensures that the
#   make_grad_cam_heatmap method finds the correct last layer for each model

def get_last_conv_layer(model):
  for layer in reversed(model.layers):
    if isinstance(layer, layers.Conv2D):
      return layer.name
  raise ValueError("No Conv2D layer found in the model.")

def make_gradcam_heatmap(img_array, model_name, model_cnn, model_resnet, model_u_net, last_conv_layer_name_cnn, last_conv_layer_name_resnet, last_conv_layer_name_u_net, pred_index=None):
    # First we select the model based on the model_name
    if model_name == 'cnn':
      model = model_cnn
      last_conv_layer_name = last_conv_layer_name_cnn
    elif model_name == 'resnet':
      model = model_resnet
      last_conv_layer_name = last_conv_layer_name_resnet
    elif model_name == 'u_net':
      model = model_u_net
      last_conv_layer_name = last_conv_layer_name_u_net
    else:
      raise ValueError("I don't recognize the name of that model.")

    print("last_conv_layer_name", last_conv_layer_name)



    # Second, we create a model that maps the input image to the activations
    # of the last conv layer as well as the output predictions
    grad_model = tf.keras.models.Model(
        [model.inputs], [model.get_layer(last_conv_layer_name).output, model.output]
    )

    # Then, we compute the gradient of the top predicted class for our input image
    # with respect to the activations of the last conv layer
    with tf.GradientTape() as tape:
        last_conv_layer_output, preds = grad_model(img_array)
        if pred_index is None:
            pred_index = tf.argmax(preds[0])
        print("pred index, ", pred_index)
        class_channel = preds[:, pred_index]

    # This is the gradient of the output neuron (top predicted or chosen)
    # with regard to the output feature map of the last conv layer
    grads = tape.gradient(class_channel, last_conv_layer_output)

    # This is a vector where each entry is the mean intensity of the gradient
    # over a specific feature map channel
    pooled_grads = tf.reduce_mean(grads, axis=(0, 1, 2))
    #pooled_grads = tf.reshape(pooled_grads, [-1,1])

    # We multiply each channel in the feature map array
    # by "how important this channel is" with regard to the top predicted class
    # then sum all the channels to obtain the heatmap class activation
    last_conv_layer_output = last_conv_layer_output[0]
    ### DEBUG
    print("DEBUG --- pooled_grads shape: ", pooled_grads.shape)
    print("DEBUG --- last_conv_layer_output shape: ", last_conv_layer_output.shape)
    ### DEBUG
    heatmap = last_conv_layer_output @ pooled_grads[..., tf.newaxis]
    heatmap = tf.squeeze(heatmap)

    # For visualization purpose, we will also normalize the heatmap between 0 & 1
    heatmap = tf.maximum(heatmap, 0) / tf.math.reduce_max(heatmap)
    return heatmap.numpy()

classifier_cnn = get_model('cnn')
classifier_resnet = get_model('resnet')
classifier_u_net = get_model('u_net')

last_conv_layer_name_cnn = get_last_conv_layer(classifier_cnn)
last_conv_layer_name_resnet = get_last_conv_layer(classifier_resnet)
last_conv_layer_name_u_net = get_last_conv_layer(classifier_u_net)

for l in classifier_cnn.layers:
  print(f"CNN: {l.name}")

for m in classifier_resnet.layers:
  print(f"RESNET: {m.name}")

for n in classifier_u_net.layers:
  print(f"U-NET: {n.name}")

test_data_paths = glob.glob("/content/drive/MyDrive/__FLOW_PATCHES/centered_CW/*.npy")
data_test = get_data_test(test_data_paths)

classifier_cnn.load_weights('/content/drive/MyDrive/__FLOW_PATCHES/model_mag/30.h5') # removed by_name = True - was causing inefficient weight error. Discrepancies with weights associated with layer names.

# Import necessary libraries
from matplotlib import cm
import numpy as np

# Set last convolutional layers for CNN and ResNet dynamically
last_conv_layer_name_cnn = get_last_conv_layer(classifier_cnn)
last_conv_layer_name_resnet = get_last_conv_layer(classifier_resnet)
last_conv_layer_name_u_net = get_last_conv_layer(classifier_u_net)

# Run through the dataset to generate heatmaps for both models
i = 0
classifier_cnn.layers[-1].activation = None
classifier_resnet.layers[-1].activation = None
classifier_u_net.layers[-1].activation = None

while i < 200:
    i += 1
    f, path = next(data_test)
    print(f.shape)

    # Get predictions and class names for CNN model
    preds_cnn = classifier_cnn.predict(f)
    maxi_cnn = np.argmax(preds_cnn[0])
    cls_cnn = ["CCW", "CW", "SADDLE"][maxi_cnn]

    # Get predictions and class names for ResNet model
    preds_resnet = classifier_resnet.predict(f)
    maxi_resnet = np.argmax(preds_resnet[0])
    cls_resnet = ["CCW", "CW", "SADDLE"][maxi_resnet]

    # Get predictions and class names for U-Net Model
    preds_u_net = classifier_u_net.predict(f)
    maxi_u_net = np.argmax(preds_cnn[0])
    cls_u_net = ["CCW", "CW", "SADDLE"][maxi_u_net]

    title_cnn = "CNN predicted class = " + cls_cnn
    title_resnet = "ResNet predicted class = " + cls_resnet
    title_u_net = "U-Net predicted class = " + cls_u_net



    # Generate Grad-CAM heatmaps for both models
    heatmap_cnn = make_gradcam_heatmap(
        f, 'cnn', classifier_cnn, classifier_resnet, classifier_u_net, last_conv_layer_name_cnn, last_conv_layer_name_resnet, last_conv_layer_name_u_net, pred_index=None
    )
    heatmap_resnet = make_gradcam_heatmap(
        f, 'resnet', classifier_cnn, classifier_resnet, classifier_u_net, last_conv_layer_name_cnn, last_conv_layer_name_resnet, last_conv_layer_name_u_net, pred_index=None
    )
    heatmap_u_net = make_gradcam_heatmap(
        f,'u_net', classifier_cnn, classifier_resnet, classifier_u_net, last_conv_layer_name_cnn, last_conv_layer_name_resnet, last_conv_layer_name_u_net, pred_index=None
    )


    # Rescale heatmaps to a range of 0-255
    heatmap_cnn = np.uint8(255 * heatmap_cnn)
    heatmap_resnet = np.uint8(255 * heatmap_resnet)
    heatmap_u_net = np.uint8(255 * heatmap_u_net)

    # Apply jet colormap to heatmaps
    jet = cm.get_cmap("jet")
    jet_colors = jet(np.arange(256))[:, :3]
    jet_heatmap_cnn = jet_colors[heatmap_cnn]
    jet_heatmap_resnet = jet_colors[heatmap_resnet]
    jet_heatmap_u_net = jet_colors[heatmap_u_net]

    # Convert the heatmaps to images
    jet_heatmap_cnn = keras.preprocessing.image.array_to_img(jet_heatmap_cnn)
    jet_heatmap_cnn = jet_heatmap_cnn.resize((f.shape[2], f.shape[1]))
    jet_heatmap_cnn = keras.preprocessing.image.img_to_array(jet_heatmap_cnn)


    jet_heatmap_resnet = keras.preprocessing.image.array_to_img(jet_heatmap_resnet)
    jet_heatmap_resnet = jet_heatmap_resnet.resize((f.shape[2], f.shape[1]))
    jet_heatmap_resnet = keras.preprocessing.image.img_to_array(jet_heatmap_resnet)

    jet_heatmap_u_net = keras.preprocessing.image.array_to_img(jet_heatmap_u_net)
    jet_heatmap_u_net = jet_heatmap_u_net.resize((f.shape[2], f.shape[1]))
    #jet_heatmap_u_net = keras.preprocessing.image.img_to_array(jet_heatmap_u_net)

    # Load U and V components from file
    m = np.load(path)
    U = m[0]
    V = m[1]
    print(U.shape)

    # Calculating Magnitude
    mag_cnn = (U**2 + V**2)**0.5
    mag_resnet = (U**2 + V**2)**0.5
    mag_u_net = (U**2 + V**2)**0.5


    # Plot the heatmaps and other components
    plt.figure(figsize=(18, 10))

    # Original image with CNN heatmap
    plt.subplot(3, 4, 1)
    plt.imshow(f[0, :, :, 0], cmap="gray")
    plt.imshow(jet_heatmap_cnn, alpha=0.4, cmap='jet')  # Overlay CNN heatmap
    plt.title("Original Image with CNN Heatmap")

    # Original image with ResNet heatmap
    plt.subplot(3, 4, 2)
    plt.imshow(f[0, :, :, 0], cmap="gray")
    plt.imshow(jet_heatmap_resnet, alpha=0.4, cmap='jet')  # Overlay ResNet heatmap
    plt.title("Original Image with ResNet Heatmap")

    # Original image with U-Net heatmap
    plt.subplot(3,4,3)
    plt.imshow(f[0, :, :, 0], cmap="gray")
    plt.imshow(jet_heatmap_u_net, alpha=0.4, cmap='jet')  # Overlay U-Net heatmap
    plt.title("Original Image with U-Net Heatmap")

   # Magnitude map for CNN
    plt.subplot(3, 4, 4)
    plt.imshow(mag_cnn, cmap="coolwarm", norm=MidpointNormalize(midpoint=0, vmin=np.min(mag_cnn), vmax=np.max(mag_cnn)))
    plt.title("Magnitude Map for CNN")

    # Magnitude map for ResNet
    plt.subplot(3, 4, 5)
    plt.imshow(mag_resnet, cmap="coolwarm", norm=MidpointNormalize(midpoint=0, vmin=np.min(mag_resnet), vmax=np.max(mag_resnet)))
    plt.title("Magnitude Map for ResNet")

    # Magnitude map for U-Net
    plt.subplot(3, 4, 6)
    plt.imshow(mag_u_net, cmap="coolwarm", norm=MidpointNormalize(midpoint=0, vmin=np.min(mag_u_net), vmax=np.max(mag_u_net)))
    plt.title("Magnitude Map for U-Net")

    # Streamplot visualization
    plt.subplot(3, 4, 7)
    nx, ny = 64, 64
    x = np.linspace(-5, 5, nx)
    y = np.linspace(-5, 5, ny)
    plt.gca().invert_yaxis()
    plt.streamplot(x, y, U, V)
    plt.title("Streamplot")

    # U component plot
    plt.subplot(3,4,8)
    plt.imshow(U, cmap="coolwarm", norm=MidpointNormalize(midpoint=0, vmin=np.min(U), vmax=np.max(U)))
    plt.colorbar(fraction=0.046, pad=0.04)
    labels = np.linspace(-4, 4, 9)
    locs = np.linspace(0, 63, 9)
    labels = ["%.1f" % l for l in labels]
    plt.xticks(locs, labels)
    plt.yticks(locs, labels)
    plt.title("U component")

    # V component plot
    plt.subplot(3, 4, 9)
    plt.imshow(V, cmap="coolwarm", norm=MidpointNormalize(midpoint=0, vmin=np.min(V), vmax=np.max(V)))
    plt.colorbar(fraction=0.046, pad=0.04)
    plt.xticks(locs, labels)
    plt.yticks(locs, labels)
    plt.title("V component")

    plt.suptitle(f"Comparison of Grad-Cam Heatmaps and Magnitude Maps for CNN and ResNet - {path}")
    plt.tight_layout()
    plt.show()


    # Save to disk if necessary
    # plt.savefig('/content/drive/MyDrive/__FLOW_PATCHES/centered_SAD_Grad_CAM/'+str(i)+".png")

    if i > 40:
        break

# def save_and_display_gradcam(img_path, heatmap, cam_path="cam.jpg", alpha=0.9):
#     # Load the original image
#     img = keras.preprocessing.image.load_img(img_path)
#     img = keras.preprocessing.image.img_to_array(img)

#     # Rescale heatmap to a range 0-255
#     heatmap = np.uint8(255 * heatmap)

#     # Use jet colormap to colorize heatmap
#     jet = cm.get_cmap("jet")

#     # Use RGB values of the colormap
#     jet_colors = jet(np.arange(256))[:, :3]
#     jet_heatmap = jet_colors[heatmap]

#     # Create an image with RGB colorized heatmap
#     jet_heatmap = keras.preprocessing.image.array_to_img(jet_heatmap)
#     jet_heatmap = jet_heatmap.resize((img.shape[1], img.shape[0]))
#     jet_heatmap = keras.preprocessing.image.img_to_array(jet_heatmap)

#     # Superimpose the heatmap on original image
#     superimposed_img = jet_heatmap * alpha + img
#     superimposed_img = keras.preprocessing.image.array_to_img(superimposed_img)

#     # Save the superimposed image
#     superimposed_img.save(cam_path)

#     # Display Grad CAM
#     display(Image(cam_path))


# save_and_display_gradcam(img_path, heatmap)

# for layer in classifier.layers:
#   g=layer.get_config()
#   h=layer.get_weights()
#   print (g)
#   print (len(h))