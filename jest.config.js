module.exports = {
  testEnvironment: 'jsdom',
  roots: ['<rootDir>/tests/unit'],
  testMatch: ["**/__tests__/**/*.?(js|ts)?(x)", "**/tests/unit/frontend/**/*.?(js|jsx|ts|tsx)"],
  moduleNameMapper: {
    '\\.(css|less|scss|sass)$': 'identity-obj-proxy',
    '^react$': '<rootDir>/node_modules/react',
    '^react-dom$': '<rootDir>/node_modules/react-dom',
    '^react-dom/client$': '<rootDir>/node_modules/react-dom/client',
    '^react/jsx-runtime$': '<rootDir>/node_modules/react/jsx-runtime',
    '^react/jsx-dev-runtime$': '<rootDir>/node_modules/react/jsx-dev-runtime',
    '^react-router-dom$': '<rootDir>/agent-ui/node_modules/react-router-dom',
    '^sonner$': '<rootDir>/agent-ui/node_modules/sonner'
  },
  transformIgnorePatterns: [
    '/node_modules/(?!(@testing-library)/)'
  ],
  setupFilesAfterEnv: ['<rootDir>/tests/unit/setup.js'],
  collectCoverageFrom: [
    'scripts/**/*.{js,jsx}',
    'agent-ui/src/**/*.{js,jsx,tsx,ts}',
    '!scripts/**/*.test.{js,jsx}',
    '!agent-ui/src/**/*.test.{js,jsx,tsx,ts}'
  ],
  coverageThreshold: {
    global: {
      statements: 70,
      branches: 70,
      functions: 70,
      lines: 70,
    }
  }
};
