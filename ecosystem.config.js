// ecosystem.config.js
module.exports = {
  apps: [
    {
      name: "pm2plus-flask",
      script: "app.py",
      interpreter: "./venv/bin/python", 
      watch: false,
      env: {
        FLASK_ENV: "production",
        PYTHONUNBUFFERED: "1",
        PORT: "3000"
      }
    }
  ]
};
