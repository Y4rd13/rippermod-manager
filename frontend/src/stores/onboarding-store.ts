import { create } from "zustand";

interface OnboardingState {
  currentStep: number;
  openaiKey: string;
  nexusKey: string;
  nexusUsername: string;
  gameName: string;
  installPath: string;
  setStep: (step: number) => void;
  setOpenaiKey: (key: string) => void;
  setNexusKey: (key: string) => void;
  setNexusUsername: (username: string) => void;
  setGameName: (name: string) => void;
  setInstallPath: (path: string) => void;
  reset: () => void;
}

export const useOnboardingStore = create<OnboardingState>((set) => ({
  currentStep: 0,
  openaiKey: "",
  nexusKey: "",
  nexusUsername: "",
  gameName: "Cyberpunk 2077",
  installPath: "",
  setStep: (step) => set({ currentStep: step }),
  setOpenaiKey: (key) => set({ openaiKey: key }),
  setNexusKey: (key) => set({ nexusKey: key }),
  setNexusUsername: (username) => set({ nexusUsername: username }),
  setGameName: (name) => set({ gameName: name }),
  setInstallPath: (path) => set({ installPath: path }),
  reset: () =>
    set({
      currentStep: 0,
      openaiKey: "",
      nexusKey: "",
      nexusUsername: "",
      gameName: "Cyberpunk 2077",
      installPath: "",
    }),
}));
