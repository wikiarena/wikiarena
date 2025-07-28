// Environment-based configuration for Wiki Arena
export interface AppConfig {
  apiBaseUrl: string;
  wsBaseUrl: string;
  environment: 'development' | 'production';
}

function getConfig(): AppConfig {
  const isDevelopment = window.location.hostname === 'localhost' || 
                       window.location.hostname === '127.0.0.1' ||
                       window.location.hostname.startsWith('192.168.') ||
                       window.location.port !== '';

  if (isDevelopment) {
    return {
      apiBaseUrl: 'http://localhost:8000',
      wsBaseUrl: 'ws://localhost:8000',
      environment: 'development'
    };
  } else {
    return {
      apiBaseUrl: 'https://wikiarena-sandbox.eba-ji9ibe4t.us-west-2.elasticbeanstalk.com',
      wsBaseUrl: 'wss://wikiarena-sandbox.eba-ji9ibe4t.us-west-2.elasticbeanstalk.com',
      environment: 'production'
    };
  }
}

export const config = getConfig();

console.log(`App running in ${config.environment} mode`);
console.log(`API Base URL: ${config.apiBaseUrl}`);
console.log(`WebSocket Base URL: ${config.wsBaseUrl}`);