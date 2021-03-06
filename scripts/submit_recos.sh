#for file in {10..25}
#for file in {26..50}
#for file in {16..17}
#for file in {18..19}
#for file in {20..29}
for file in {0..19}
#for file in {26..30}
#for file in {20..25}
do
for dir in {0..99}
do
#    echo "/storage/home/pde3/retro/scripts/reco_file.sh $dir $file" | qsub -A cyberlamp \
#-l qos=cl_open \
#    echo "/storage/home/pde3/retro/scripts/reco_file.sh $dir $file" | qsub -A dfc13_b_g_sc_default \
#    echo "/storage/home/pde3/retro/scripts/reco_file.sh $dir $file" | qsub -A open \
#-l qos=cl_open \
#    echo "/storage/home/pde3/retro/scripts/reco_file.sh $dir $file" | qsub -A cyberlamp \
#    echo "/storage/home/pde3/retro/scripts/reco_file.sh $dir $file" | qsub -A dfc13_a_g_sc_default \
#    echo "/storage/home/pde3/retro/scripts/reco_file.sh $dir $file" | qsub -A cyberlamp -l qos=cl_open \
#    echo "/storage/home/pde3/retro/scripts/reco_file.sh $dir $file" | qsub -A dfc13_b_g_lc_default \
#    echo "/storage/home/pde3/retro/scripts/reco_file.sh $dir $file" | qsub -A open \
    echo "/storage/home/pde3/retro/scripts/reco_file.sh $dir $file" | qsub -A cyberlamp \
-l nodes=1:ppn=1 \
-l pmem=4000mb \
-l walltime=12:00:00 \
-N r$dir.$file \
-o /gpfs/scratch/pde3/retro/log/$dir.$file.log \
-e /gpfs/scratch/pde3/retro/log/$dir.$file.err
done
done
