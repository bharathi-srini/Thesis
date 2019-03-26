from keras.models import Model
from keras.layers.core import Dense, Reshape, Lambda
from keras.layers import Input, Embedding, merge
from keras import backend as K
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from keras import preprocessing
from keras.regularizers import l2
import random
from keras.layers.advanced_activations import LeakyReLU


def first_prod(order):
    for _,row in order.iterrows():
        if row['add_to_cart_order']==1:
            return row['product_id']

def next_prod(order):
    for _,row in order.iterrows():
        if row['add_to_cart_order']==2:
            return row['product_id']

def create_basket(order):
    order['product_id']= order['product_id'].astype(str)
    
    basket = []
    for _,row in order.iterrows():
        if row['add_to_cart_order']!=1:
            basket.append(row['product_id'])
    #basket = random.shuffle(basket)
    return basket

def transform_data_for_embedding(df):
    first = df.groupby(['order_id']).apply(first_prod)
    next_prod = df.groupby(['order_id']).apply(lambda x:next_prod(x))
    basket =df.groupby(['order_id']).apply(lambda x: create_basket(x))
    
    transform_df = pd.DataFrame(first, columns = ['first_prod'])
    transform_df['next_prod']= pd.DataFrame(next_prod)
    transform_df['basket']= pd.DataFrame(basket)

    # Number of product IDs available
    N_products = df['product_id'].nunique()
    N_shoppers = df['user_id'].nunique()

    return transform_df, N_products, N_shoppers

def create_input_for_embed_network(df, transform_df, N_products):

    # Creating df with order_id, user_id, first prod, next prod, basket 
    transform_df.reset_index(inplace=True)
    x = df.drop_duplicates(subset=['order_id','user_id'])
    train_df = pd.merge(transform_df, x[['order_id','user_id']], how='left', on='order_id' )
    train_df.dropna(inplace=True)

    # Creating basket as categorical matrix for deep neural network output
    names = []
    for col in range(N_products):
        names.append('col_' + str(col)) 

    basket_df = pd.DataFrame(columns= names)
    for i,row in train_df.iterrows():
        for val in row.basket:
            if val!=0:
                basket_df.loc[i,'col_'+val] = 1
    basket_df.fillna(0, inplace=True)

    train_df['next_prod'] = train_df['next_prod'].astype('category', categories = df_use.product_id.unique())
    y_df = pd.get_dummies(train_df, columns = ['next_prod'])
    y_df.drop(['user_id','order_id','first_prod','basket'], axis=1, inplace=True)
    
    train_df.drop(['order_id','next_prod','basket'], axis=1, inplace=True)

    return train_df['first_prod'], train_df['user_id'], basket_df, y_df

def create_embedding_network(N_products, N_shoppers, prior_in, shopper_in, candidates_in, predicted ):

    # Integer IDs representing 1-hot encodings
    prior_in = Input(shape=(1,))
    shopper_in = Input(shape=(1,))

    # Dense N-hot encoding for candidate products
    candidates_in = Input(shape=(N_products,))

    # Embeddings
    prior = Embedding(N_products+1, 10)(prior_in)
    shopper = Embedding(N_shoppers+1, 10)(shopper_in)

    # Reshape and merge all embeddings together
    reshape = Reshape(target_shape=(10,))
    combined = merge([reshape(prior), reshape(shopper)],
                 mode='concat')

    # Hidden layers
    #hidden_1 = Dense(1024, activation='relu',W_regularizer=l2(0.02))(combined)
    #hidden_2 = Dense(512, activation='relu',W_regularizer=l2(0.02))(hidden_1)
    hidden_3 = Dense(100, activation='relu')(combined)
    hidden_4 = Dense(1, activation='relu')(hidden_3)

    # Final 'fan-out' into the space of future products
    final = Dense(N_products, activation='relu')(hidden_4)

    # Ensure we do not overflow when we exponentiate
    final = Lambda(lambda x: x - K.max(x))(final)

    # Masked soft-max using Lambda and merge-multiplication
    exponentiate = Lambda(lambda x: K.exp(x))(final)
    masked = merge([exponentiate, candidates_in], mode='mul')
    predicted = Lambda(lambda x: x / K.sum(x))(masked)

    # Compile with categorical crossentropy and adam
    mdl = Model(input=[prior_in, shopper_in, candidates_in],
            output=predicted)
    mdl.compile(loss='categorical_crossentropy', 
            optimizer='adam',
            metrics=['accuracy'])

    mdl.fit([prior_in, shopper_in, candidates_in], predicted,  batch_size=128, epochs=3, verbose=1)

