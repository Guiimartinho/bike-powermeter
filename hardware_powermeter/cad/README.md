# CAD

A cadeia é a mesma do ciclocomputador (`make_pcb.py` → `route.py` → `fill_zones.py` com o Python do KiCad → `check_pcb.py --como-esta` → `dry_run_pcb.py` → `make_3d.py` → `make_2d.py` → `montagem.py`), a portar quando o esquemático (`nets.py`) existir. As armadilhas medidas lá valem aqui: modelos 3D conferidos por medida, regras que falham quando não acham o que medir, roteador e verificador lendo o `.kicad_pcb`.
