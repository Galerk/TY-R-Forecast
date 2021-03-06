import os
import time
import datetime as dt
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from torchvision import transforms

# from src.tools.easyparser import *
from src.tools.parser import get_args
from src.tools.loss import Loss
from src.tools.utils import save_model, get_logger
from src.dataseters.GRUs import TyDataset, ToTensor, Normalize
from src.operators.transformer import *

def train_epoch(model, dataloader, optimizer, args, logger):
	time_s = time.time()
	model.train()

	tmp_loss = 0
	total_loss = 0
	device = args.device
	dtype = args.value_dtype
	loss_function = args.loss_function

	total_idx = len(dataloader)

	for idx, data in enumerate(dataloader,0):
		src = data['inputs'].to(device=device, dtype=dtype)
		tgt = data['targets'].to(device=device, dtype=dtype).unsqueeze(2)
		src_mask = torch.ones(1, src.shape[1]).to(device=device, dtype=dtype)
		tgt_mask = subsequent_mask(tgt.shape[1]).to(device=device, dtype=dtype)
		pred = model(src, tgt, src_mask, tgt_mask)
		
		optimizer.zero_grad()
		
		loss = loss_function(pred, tgt.squeeze(2))
		loss.backward()
		
		optimizer.step()
		
		tmp_loss += loss.item()/(total_idx//3)
		total_loss += loss.item()/total_idx
		
		if (idx+1) % (total_idx//3) == 0:
			logger.debug('[{:s}] Training Process: {:d}/{:d}, Loss = {:.2f}'.format(args.model, idx+1, total_idx, tmp_loss))
			tmp_loss = 0
			
	time_e =time.time()
	time_step = (time_e-time_s)/60

	logger.debug('[{:s}] Training Process: Ave_Loss = {:.2f} Time spend: {:.1f} mins'.format(args.model, total_loss, time_step))
	
	return total_loss

def eval_epoch(model, dataloader, args, logger):
	time_s = time.time()
	model.eval()

	tmp_loss = 0
	total_loss = 0
	device = args.device
	dtype = args.value_dtype
	loss_function = args.loss_function

	total_idx = len(dataloader)

	with torch.no_grad():
		for idx, data in enumerate(dataloader,0):
			src = data['inputs'].to(device=device,dtype=dtype)
			tgt = data['targets'].to(device=device,dtype=dtype).unsqueeze(2)
			src_mask = torch.ones(1, src.shape[1]).to(device=device,dtype=dtype)
			tgt_mask = subsequent_mask(tgt.shape[1]).to(device=device,dtype=dtype)
			pred = model(src, tgt, src_mask, tgt_mask)
			
			loss = loss_function(pred, tgt.squeeze(2))
			total_loss += loss.item()/total_idx 
		
	time_e =time.time()
	time_step = (time_e-time_s)/60
	logger.debug('[{:s}] Validating Process: {:d} samples, Loss = {:.2f} Time spend: {:.1f} mins'.format(args.model, total_idx*args.batch_size, total_loss, time_step))
			

	return total_loss


def infer_epoch(model, dataloader, args, logger):
	time_s = time.time()
	model.eval()

	tmp_loss = 0
	total_loss = 0
	device = args.device
	dtype = args.value_dtype
	loss_function = args.loss_function

	total_idx = len(dataloader)

	with torch.no_grad():
		for idx, data in enumerate(dataloader,0):
			src = data['inputs'].to(device=device,dtype=dtype)
			tgt = data['targets'].to(device=device,dtype=dtype).unsqueeze(2)
			pred = torch.zeros_like(tgt).to(device=device,dtype=dtype)
			src_mask = torch.ones(1, src.shape[1]).to(device=device,dtype=dtype)
			tgt_mask = subsequent_mask(tgt.shape[1]).to(device=device,dtype=dtype)
			for i in range(pred.shape[1]):
				pred[:,i,0] = (model(src, pred, src_mask, tgt_mask)[:,i]).detach()
			
			loss = loss_function(pred, tgt)
			total_loss += loss.item()/total_idx
		
	time_e = time.time()
	time_step = (time_e-time_s)/60

	logger.debug('[{:s}] Inference Process: {:d} samples, Loss = {:.2f} Time spend: {:.1f} mins'.format(args.model, total_idx*args.batch_size, total_loss, time_step))

	return total_loss
if __name__ == '__main__':
	args = get_args()
	# print(settings.initial_args)
	# settings.initial_args.gpu = 0
	# settings.initial_args.I_size = 150
	# settings.initial_args.F_size = 150
	# settings.initial_args.batch_size = 3
	# settings.initial_args.max_epochs = 100
	# args = settings.get_args()
	# args.weight_decay = 0.2
	torch.cuda.set_device(args.gpu)
	np.random.seed(args.seed)
	torch.manual_seed(args.seed)
	torch.cuda.manual_seed(args.seed)

	## dataloader
	# set transform tool for datasets
	if args.normalize_input:
		transform = transforms.Compose([ToTensor(), Normalize(args)])
	else:
		transform = transforms.Compose([ToTensor()])

	# training and validating data
	trainset = TyDataset(args, train=True, transform=transform)
	valiset = TyDataset(args, train=False, transform=transform)

	# dataloader
	train_kws = {'num_workers': 4, 'pin_memory': True} if args.able_cuda else {}
	test_kws = {'num_workers': 4, 'pin_memory': True} if args.able_cuda else {}

	trainloader = DataLoader(dataset=trainset, batch_size=args.batch_size, shuffle=True, **train_kws)
	valiloader = DataLoader(dataset=valiset, batch_size=args.batch_size, shuffle=False, **test_kws)
	# testloader = DataLoader(dataset=valiset, batch_size=args.batch_size, shuffle=False, **test_kws)

	model = make_model(H=args.I_size, W=args.I_size, input_channel=1, d_channel=5, d_channel_ff=10, dropout=args.dropout) \
						.to(device=args.device, dtype=args.value_dtype)

	optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
	lr_scheduler = torch.optim.lr_scheduler.ExponentialLR(optimizer, gamma=0.9)

	loss_df = pd.DataFrame([],index=pd.Index(range(args.max_epochs), name='Epoch'), columns=['Train_loss', 'Vali_loss', 'Vali_infer_loss'])
	
	log_file = os.path.join(args.result_folder, 'log.txt')
	loss_file = os.path.join(args.result_folder, 'loss.csv')
	logger = get_logger(log_file)

	for epoch in range(args.max_epochs):
		lr = optimizer.param_groups[0]['lr']
		logger.debug('[{:s}] Epoch {:03d}, Learning rate: {}'.format(args.model, epoch+1, lr))
 
		loss_df.iloc[epoch,0] = train_epoch(model, trainloader, optimizer, args, logger)
		loss_df.iloc[epoch,1] = eval_epoch(model, valiloader, args, logger)
		loss_df.iloc[epoch,2] = infer_epoch(model, valiloader, args, logger)

		if (epoch+1) > 10:
			lr_scheduler.gamma = 0.95
		lr_scheduler.step()

		if (epoch+1) % 10 == 0:
			save_model(epoch, optimizer, model, args)

	loss_df.to_csv(loss_file)