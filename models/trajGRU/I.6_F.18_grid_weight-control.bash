python trajGRU_run.py \
	--gpu 1	\
	--lr-scheduler	\
	--weigjt-decay 100 \
	--input-with-grid	\
	--clip	\
    --root-dir 01_Radar_data/02_numpy_files	\
    --ty-list-file ty_list.xlsx	\
    --result-dir 04_results/server	\
    --I-lat-l 24.6625 --I-lat-h 25.4 --I-lon-l 121.15 --I-lon-h 121.8875 \
    