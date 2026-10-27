import { create } from 'zustand'

interface FilterState {
  ptRatio: number
  setPtRatio: (value: number) => void
}

export const useFilterStore = create<FilterState>((set) => ({
  ptRatio: 50,
  setPtRatio: (value) => set({ ptRatio: value }),
}))