import { vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

// jsdom não implementa play/pause/load de verdade — sem isso,
// qualquer teste que chame audio.play() quebra com "not implemented"
Object.defineProperty(window.HTMLMediaElement.prototype, 'play', {
  configurable: true,
  value: vi.fn().mockResolvedValue(undefined),
})
Object.defineProperty(window.HTMLMediaElement.prototype, 'pause', {
  configurable: true,
  value: vi.fn(),
})
Object.defineProperty(window.HTMLMediaElement.prototype, 'load', {
  configurable: true,
  value: vi.fn(),
})