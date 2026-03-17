# Usamos la imagen oficial ya lista para usar
FROM atendahq/evolution-api:latest

# Configuramos el puerto
ENV PORT=8080
EXPOSE 8080

# No necesitamos instalar git ni clonar nada, la imagen ya trae todo
CMD ["node", "dist/main.js"]
