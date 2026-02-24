import { create } from "zustand";

interface OnboardingState {
  currentStep: number;
  openaiKey: string;
  nexusUsername: string;
  gameName: string;
  installPath: string;
  setStep: (step: number) => void;
  setOpenaiKey: (key: string) => void;
  setNexusUsername: (username: string) => void;
  setGameName: (name: string) => void;
  setInstallPath: (path: string) => void;
  reset: () => void;
}

export const useOnboardingStore = create<OnboardingState>((set) => ({
  currentStep: 0,
  openaiKey: "",
  nexusUsername: "",
  gameName: "Cyberpunk 2077",
  installPath: "",
  setStep: (step) => set({ currentStep: step }),
  setOpenaiKey: (key) => set({ openaiKey: key }),
  setNexusUsername: (username) => set({ nexusUsername: username }),
  setGameName: (name) => set({ gameName: name }),
  setInstallPath: (path) => set({ installPath: path }),
  reset: () =>
    set({
      currentStep: 0,
      openaiKey: "",
      nexusUsername: "",
      gameName: "Cyberpunk 2077",
      installPath: "",
    }),
}));
