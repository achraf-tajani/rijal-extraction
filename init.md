# RunPod Cheatsheet

## Connexion SSH
```bash
ssh -i /drives/c/Users/TON_NOM/.ssh/id_runpod TON_USER@ssh.runpod.io
```

---

## Installation complète (après chaque redémarrage)
```bash
apt-get update && apt-get install -y zstd && curl -fsSL https://ollama.com/install.sh | sh
```

---

## Variables d'environnement (.bashrc)
```bash
cat >> ~/.bashrc << 'EOF'
export TMPDIR=/workspace/tmp
export OLLAMA_MODELS=/workspace/ollama/models
export CUDA_VISIBLE_DEVICES=0
export OLLAMA_HOST=0.0.0.0:11434
EOF
mkdir -p /workspace/tmp /workspace/ollama/models
source ~/.bashrc
```

---

## Lancer Ollama
```bash
ollama serve > /workspace/ollama.log 2>&1 &
sleep 3 && tail -5 /workspace/ollama.log
```

---

## Script de démarrage automatique
```bash
cat > /workspace/start.sh << 'EOF'
#!/bin/bash
apt-get update -qq && apt-get install -y -qq zstd
curl -fsSL https://ollama.com/install.sh | sh
cat >> ~/.bashrc << 'BASHRC'
export TMPDIR=/workspace/tmp
export OLLAMA_MODELS=/workspace/ollama/models
export CUDA_VISIBLE_DEVICES=0
export OLLAMA_HOST=0.0.0.0:11434
BASHRC
source ~/.bashrc
mkdir -p /workspace/tmp /workspace/ollama/models
ollama serve > /workspace/ollama.log 2>&1 &
EOF
chmod +x /workspace/start.sh
```

Lancer le script :
```bash
bash /workspace/start.sh
```

---

## Modèles Ollama
```bash
# Lister les modèles
ollama list

# Télécharger un modèle
ollama pull qwen2.5:32b
ollama pull qwen2.5:72b
ollama pull qwen3-coder:latest

# Supprimer un modèle
ollama rm qwen2.5:32b

# Tester un modèle
ollama run qwen2.5:32b "dis bonjour"
```

---

## Vérifier le GPU
```bash
# Infos GPU
nvidia-smi

# Surveiller en temps réel
watch nvidia-smi

# VRAM utilisée
nvidia-smi --query-gpu=memory.used,memory.free --format=csv
```

---

## Vérifier l'espace disque
```bash
# Vue globale
df -h

# Workspace seulement
df -h /workspace

# Ce qui prend le plus de place
du -sh /workspace/*
du -sh /* 2>/dev/null | sort -rh | head -10
```

---

## Logs Ollama
```bash
# Dernières lignes
tail -20 /workspace/ollama.log

# En temps réel
tail -f /workspace/ollama.log
```

---

## Tester l'API depuis le PC
```bash
# Lister les modèles
curl https://TON_POD_ID-11434.proxy.runpod.net/api/tags

# Tester une génération
curl https://TON_POD_ID-11434.proxy.runpod.net/api/generate \
  -d '{"model":"qwen2.5:32b","prompt":"bonjour","stream":false}'
```

---

## Nettoyer l'espace
```bash
# Vider le cache apt
apt-get clean && rm -rf /var/cache/apt/archives/*

# Supprimer modèles partiels dans /root
rm -rf /root/.ollama/models/blobs/*

# Tuer Ollama
pkill ollama
```

---

## Garder la session SSH active
```bash
while true; do sleep 60; done &
```

---

## Infos pod
```bash
# Processus en cours
ps aux | grep ollama

# Mémoire RAM
free -h

# Ports ouverts
ss -tlnp | grep 11434
```

---

## URL API RunPod
```
https://TON_POD_ID-11434.proxy.runpod.net
```

Remplace `TON_POD_ID` par l'ID de ton pod (ex: `jrvl6x35ikvga6`).

---

## Config OpenCode
```
ID fournisseur  : runpod-ollama
Nom             : RunPod Ollama
URL de base     : https://TON_POD_ID-11434.proxy.runpod.net/v1
Clé API         : vide
Modèle ID       : qwen2.5:32b
Modèle Nom      : Qwen2.5 32B
```