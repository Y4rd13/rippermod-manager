import { create } from "zustand";

interface OnboardingState {
  currentStep: number;
  nexusUsername: string;
  gameName: string;
  installPath: string;
  setStep: (step: number) => void;
  setNexusUsername: (username: string) => void;
  setGameName: (name: string) => void;
  setInstallPath: (path: string) => void;
  reset: () => void;
}

export const useOnboardingStore = create<OnboardingState>((set) => ({
  currentStep: 0,
  nexusUsername: "",
  gameName: "Cyberpunk 2077",
  installPath: "",
  setStep: (step) => set({ currentStep: step }),
  setNexusUsername: (username) => set({ nexusUsername: username }),
  setGameName: (name) => set({ gameName: name }),
  setInstallPath: (path) => set({ installPath: path }),
  reset: () =>
    set({
      currentStep: 0,
      nexusUsername: "",
      gameName: "Cyberpunk 2077",
      installPath: "",
    }),
}));
