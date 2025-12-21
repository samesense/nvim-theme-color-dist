python role_clusters.py ../data/raw/photos/blueMosqueCeil.png \
  --roles 8 \
  --out-prefix blue_mosque

python assign_roles.py \
  blue_mosque_colors.csv \
  ../data/raw/nvim/lua/catppuccin/palettes/mocha.csv \
  roles_tmp.csv \
  --palette mocha

# python role_clusters.py ../data/raw/photos/abstractBoxes.png \
#   --roles 8 \
#   --out-prefix abstract_boxes
