#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Nov 14 18:20:51 2018

@author: fenqiang
"""

import torch
import torch.nn as nn
from torch.nn import init

import torchvision
import scipy.io as sio 
import numpy as np
import glob
import os

from tensorboardX import SummaryWriter
writer = SummaryWriter('log/sex')

from spherical_gan import ResNet

class BrainSphere(torch.utils.data.Dataset):

    def __init__(self, root1, root2 = None, root3 = None, root4 = None):

        self.files = sorted(glob.glob(os.path.join(root1, '*.Y1')))    
        if root2 is not None:
            self.files = self.files + sorted(glob.glob(os.path.join(root2, '*.Y1')))
        if root3 is not None:
            self.files = self.files + sorted(glob.glob(os.path.join(root3, '*.Y1')))
        if root4 is not None:
            self.files = self.files + sorted(glob.glob(os.path.join(root4, '*.Y1')))
            
        with open('/media/fenqiang/DATA/unc/Data/malelist.txt') as f1:
            self.male = f1.readlines()
            for i in range(len(self.male)):
                self.male[i] = self.male[i].strip()[1:-1]
   
        with open('/media/fenqiang/DATA/unc/Data/femalelist.txt') as f1:
            self.female = f1.readlines()
            for i in range(len(self.female)):
                self.female[i] = self.female[i].strip()[1:-1]

    def __getitem__(self, index):
        file = self.files[index]
        data = sio.loadmat(file)
        data = data['data'][:,[1,2]]
        data = (data - np.tile(np.mean(data,0), (len(data),1)))/np.tile(np.std(data,0), (len(data),1))
        
        data = (data - np.tile(np.min(data,0), (len(data),1)))/(np.tile(np.max(data,0), (len(data),1)) - np.tile(np.min(data,0), (len(data),1)))
        data = data * 2.0 - 1.0
        
        if file.split('/')[-1][0:-3] in self.male:
            label = 0
        elif file.split('/')[-1][0:-3] in self.female:
            label = 1
        else:
            print('no female or male info, ', file)
                
        return data.astype(np.float32), label

    def __len__(self):
        return len(self.files)



cuda0 = torch.device('cuda:1') 
learning_rate = 0.001
momentum = 0.99
weight_decay = 0.0001
batch_size = 1
fold1 = '/media/fenqiang/DATA/unc/Data/sex_classify/fold1'
fold2 = '/media/fenqiang/DATA/unc/Data/sex_classify/fold2'
fold3 = '/media/fenqiang/DATA/unc/Data/sex_classify/fold3'
fold5 = '/media/fenqiang/DATA/unc/Data/sex_classify/fold5'
train_dataset = BrainSphere(fold1, fold2, fold3)
train_dataloader = torch.utils.data.DataLoader(train_dataset, batch_size=batch_size, shuffle=True, pin_memory=True)
val_dataset = BrainSphere(fold5)
val_dataloader = torch.utils.data.DataLoader(val_dataset, batch_size=batch_size, shuffle=False, pin_memory=True)

conv_type = "DiNe"   # "RePa" or "DiNe"
pooling_type = "mean"  # "max" or "mean" 
model = ResNet()


print("{} paramerters in total".format(sum(x.numel() for x in model.parameters())))
model.cuda(cuda0)
criterion = nn.CrossEntropyLoss()
optimizer = torch.optim.SGD(model.parameters(), lr=learning_rate, momentum=momentum, weight_decay=weight_decay)
#optimizer = torch.optim.Adam(model.parameters(),lr=learning_rate,  betas=(0.8, 0.999))
#scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, 'min', factor=0.1, patience=1, verbose=True, threshold=0.0001, threshold_mode='rel')


def train_step(data, target):
    model.train()
    data, target = data.cuda(cuda0), target.cuda(cuda0)

    prediction = model(data)
    
    loss = criterion(prediction, target)

    optimizer.zero_grad()
    loss.backward()
    optimizer.step()

    return loss.item()

def get_learning_rate(epoch):
    limits = [2, 4, 7]
    lrs = [1, 0.1, 0.05, 0.005]
    assert len(lrs) == len(limits) + 1
    for lim, lr in zip(limits, lrs):
        if epoch < lim:
            return lr * learning_rate
    return lrs[-1] * learning_rate

def val_during_training():
    model.eval()

    correct_num = 0
    for batch_idx, (data, target) in enumerate(val_dataloader):
        data = data.squeeze().cuda(cuda0)
        with torch.no_grad():
            prediction = model(data)
        
        prediction = prediction.max(1)[1]
        if prediction.cpu() == target:
            correct_num = correct_num + 1
            
    return correct_num/len(val_dataloader)

def val_train_during_training():
    model.eval()

    correct_num = 0
    for batch_idx, (data, target) in enumerate(train_dataloader):
        data = data.squeeze().cuda(cuda0)
        with torch.no_grad():
            prediction = model(data)
        
        prediction = prediction.max(1)[1]
        if prediction.cpu() == target:
            correct_num = correct_num + 1
            
    return correct_num/len(train_dataloader)


for epoch in range(300):
    
    train_acc  = val_train_during_training()
    print("Train acc {:.4}".format(train_acc))
    val_acc = val_during_training()
    print("Val acc: {:.4}".format(val_acc))
    writer.add_scalars('data/acc', {'train': train_acc, 'val': val_acc}, epoch)

    lr = get_learning_rate(epoch)
    for p in optimizer.param_groups:
        p['lr'] = lr
        print("learning rate = {}".format(p['lr']))
    
#    dataiter = iter(train_dataloader)
#    data, target = dataiter.next()
    
    for batch_idx, (data, target) in enumerate(train_dataloader):
        data = data.squeeze()
        loss = train_step(data, target)

        print("[{}:{}/{}]  LOSS={:.4}".format(epoch, 
              batch_idx, len(train_dataloader), loss))
        
        writer.add_scalar('Train/Loss', loss, epoch*len(train_dataloader) + batch_idx)


    
#    scheduler.step(scheduler_loss)
#
#    train_dice[epoch % 5] = a
#    print("last five train Dice: ",train_dice)
#    if np.std(np.array(train_dice)) <= 0.00001:
#        torch.save(model.state_dict(), os.path.join("state.pkl"))
#        break
#
    if epoch % 2 == 0:
       # a = val_train_during_training()
        #print("train Dice:", a)
        torch.save(model.state_dict(), os.path.join("sex.pkl"))
#  



