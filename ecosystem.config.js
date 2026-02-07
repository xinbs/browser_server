module.exports = {
  apps: [{
    name: "browser-server",
    script: "./browser_server.py",
    interpreter: "python",
    cwd: "D:\\Code\\browser_user",
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: "2G",
    env: {
      BROWSER_HOST: "0.0.0.0",
      BROWSER_PORT: "3456",
      BROWSER_USER_DATA_DIR: "D:\\Code\\browser_user\\user_data",
      BROWSER_HEADLESS: "true",
      PYTHONUNBUFFERED: "1"
    },
    windowsHide: false,
    log_file: "D:\\Code\\browser_user\\logs\\combined.log",
    out_file: "D:\\Code\\browser_user\\logs\\out.log",
    err_file: "D:\\Code\\browser_user\\logs\\error.log",
    log_date_format: "YYYY-MM-DD HH:mm:ss Z"
  }]
};
