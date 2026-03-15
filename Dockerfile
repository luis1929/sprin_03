FROM node:20-alpine

# Instalamos git (sin el error del cls)
RUN apk add --no-cache git

# Directorio de trabajo
WORKDIR /app

# Clonamos la versión oficial de Evolution API
RUN git clone https://github.com/EvolutionAPI/evolution-api.git .

# Instalamos dependencias
RUN npm ci --only=production

# Exponemos el puerto que Railway espera
EXPOSE 8080

# Comando de arranque
CMD ["npm", "start"]