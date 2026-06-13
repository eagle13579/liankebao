/**
 * Jest config for WeChat miniprogram testing with miniprogram-simulate
 */
module.exports = {
  testEnvironment: 'jsdom',
  testEnvironmentOptions: {
    url: 'https://jest.test'
  },
  testMatch: [
    '**/__tests__/**/*.test.js'
  ],
  moduleFileExtensions: ['js', 'json'],
  // miniprogram-simulate needs these transforms
  transformIgnorePatterns: [
    'node_modules/(?!(miniprogram-simulate|j-component)/)'
  ],
  // Collect coverage from source pages
  collectCoverageFrom: [
    'pages/**/*.js',
    '!**/node_modules/**'
  ],
  // Snapshot plugin for miniprogram-simulate
  snapshotSerializers: [
    'miniprogram-simulate/jest-snapshot-plugin'
  ]
}
