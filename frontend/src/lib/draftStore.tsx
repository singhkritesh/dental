import { createContext, type ReactNode, useContext, useMemo, useState } from "react";

type Seed = {
  content: string;
  version: number;
};

type DraftStoreContextValue = {
  emailSeed: Seed;
  denialSeed: Seed;
  loadToEmail: (content: string) => void;
  loadToDenial: (content: string) => void;
};

const DraftStoreContext = createContext<DraftStoreContextValue | null>(null);

export function DraftStoreProvider({ children }: { children: ReactNode }) {
  const [emailSeed, setEmailSeed] = useState<Seed>({ content: "", version: 0 });
  const [denialSeed, setDenialSeed] = useState<Seed>({ content: "", version: 0 });

  const value = useMemo<DraftStoreContextValue>(
    () => ({
      emailSeed,
      denialSeed,
      loadToEmail(content: string) {
        setEmailSeed((current) => ({
          content,
          version: current.version + 1
        }));
      },
      loadToDenial(content: string) {
        setDenialSeed((current) => ({
          content,
          version: current.version + 1
        }));
      }
    }),
    [emailSeed, denialSeed]
  );

  return <DraftStoreContext.Provider value={value}>{children}</DraftStoreContext.Provider>;
}

export function useDraftStore(): DraftStoreContextValue {
  const context = useContext(DraftStoreContext);
  if (!context) {
    throw new Error("useDraftStore must be used inside DraftStoreProvider.");
  }
  return context;
}

