import { create } from 'zustand'

interface UiState {
  navigationCollapsed: boolean
  toggleNavigation: () => void
}

export const useUiStore = create<UiState>((set) => ({
  navigationCollapsed: false,
  toggleNavigation: () => set((state) => ({ navigationCollapsed: !state.navigationCollapsed })),
}))
