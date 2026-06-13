/**
 * Smart AI Agent Configuration
 * 
 * Configuration for the autonomous bulletin extraction agent system.
 * This replaces the passive Gemini advice system with an active agent
 * that can plan, execute actions, and verify results.
 */

const AGENT_CONFIG = {
  // Primary AI model for planning and verification
  primary: {
    provider: 'openai',
    model: 'gpt-4o-mini',
    temperature: 0.7,
    maxTokens: 2000,
  },

  // Fallback model for tough cases (optional, can be disabled to save costs)
  fallback: {
    enabled: false, // Set to true if you want Claude backup
    provider: 'anthropic',
    model: 'claude-3-5-sonnet-20241022',
    temperature: 0.7,
    maxTokens: 2000,
    useWhen: 'primaryFailsThrice', // or 'always', 'never'
  },

  // Vision/screenshot analysis settings
  vision: {
    enabled: true,
    useWhen: 'needed', // 'always', 'needed', or 'never'
    maxImageSize: 1024 * 1024, // 1MB max
    compressionQuality: 0.8,
  },

  // Learning and pattern matching
  learning: {
    enabled: true,
    saveSuccessfulPatterns: true,
    tryPatternsFirst: true, // Use learned patterns before AI
    confidenceThreshold: 0.75, // Minimum confidence to use pattern
    maxPatternAge: 90, // Days before pattern considered stale
  },

  // Verification settings
  verification: {
    enabled: true,
    checkBulletinWeek: true,
    checkFileValidity: true,
    allowManualOverride: true,
  },

  // Budget and cost controls
  budget: {
    maxCostPerParish: 0.02, // 2 cents per parish max
    usePatternMatchingWhenPossible: true,
    skipVisionForKnownPatterns: true,
    warnOnHighCost: true,
  },

  // Retry and error handling
  retry: {
    maxAttempts: 3,
    backoffMs: 1000,
    useAlternativeStrategiesOnFail: true,
  },

  // Logging
  logging: {
    enabled: true,
    logLevel: 'info', // 'debug', 'info', 'warn', 'error'
    logToConsole: true,
    logToStorage: true,
    maxLogEntries: 1000,
  },
};

// API endpoints
const API_ENDPOINTS = {
  openai: 'https://api.openai.com/v1/chat/completions',
  anthropic: 'https://api.anthropic.com/v1/messages',
};

// Storage keys
const STORAGE_KEYS = {
  openaiKey: 'openai_api_key',
  anthropicKey: 'anthropic_api_key',
  mistralKey: 'mistral_api_key', // Keep for backward compatibility
  geminiKey: 'gemini_api_key', // Keep for backward compatibility
  patterns: 'agent_learned_patterns',
  logs: 'agent_logs',
  stats: 'agent_stats',
};

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { AGENT_CONFIG, API_ENDPOINTS, STORAGE_KEYS };
}
