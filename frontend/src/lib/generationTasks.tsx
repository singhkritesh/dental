import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";

export type GenerationTaskStatus = "idle" | "running" | "success" | "error";

export type GenerationTaskRecord = {
  key: string;
  status: GenerationTaskStatus;
  startedAt?: number;
  finishedAt?: number;
  result?: unknown;
  error?: unknown;
};

type GenerationTaskContextValue = {
  tasks: Record<string, GenerationTaskRecord>;
  runTask: <T>(key: string, runner: () => Promise<T>) => Promise<T>;
  getInFlight: <T>(key: string) => Promise<T> | null;
  clearTask: (key: string) => void;
};

const GenerationTaskContext = createContext<GenerationTaskContextValue | null>(null);

export function GenerationTaskProvider({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useState<Record<string, GenerationTaskRecord>>({});
  const inFlightRef = useRef<Record<string, Promise<unknown>>>({});

  const runTask = useCallback(
    async <T,>(key: string, runner: () => Promise<T>): Promise<T> => {
      const existing = inFlightRef.current[key] as Promise<T> | undefined;
      if (existing) {
        return existing;
      }

      setTasks((current) => ({
        ...current,
        [key]: {
          key,
          status: "running",
          startedAt: Date.now(),
        },
      }));

      const promise = runner();
      inFlightRef.current[key] = promise;

      try {
        const result = await promise;
        setTasks((current) => ({
          ...current,
          [key]: {
            key,
            status: "success",
            startedAt: current[key]?.startedAt ?? Date.now(),
            finishedAt: Date.now(),
            result,
          },
        }));
        return result;
      } catch (error) {
        setTasks((current) => ({
          ...current,
          [key]: {
            key,
            status: "error",
            startedAt: current[key]?.startedAt ?? Date.now(),
            finishedAt: Date.now(),
            error,
          },
        }));
        throw error;
      } finally {
        delete inFlightRef.current[key];
      }
    },
    []
  );

  const getInFlight = useCallback(<T,>(key: string): Promise<T> | null => {
    return (inFlightRef.current[key] as Promise<T> | undefined) ?? null;
  }, []);

  const clearTask = useCallback((key: string) => {
    setTasks((current) => {
      if (!current[key]) {
        return current;
      }
      const next = { ...current };
      delete next[key];
      return next;
    });
    delete inFlightRef.current[key];
  }, []);

  const value = useMemo<GenerationTaskContextValue>(
    () => ({
      tasks,
      runTask,
      getInFlight,
      clearTask,
    }),
    [tasks, runTask, getInFlight, clearTask]
  );

  return <GenerationTaskContext.Provider value={value}>{children}</GenerationTaskContext.Provider>;
}

export function useGenerationTasks(): GenerationTaskContextValue {
  const context = useContext(GenerationTaskContext);
  if (!context) {
    throw new Error("useGenerationTasks must be used inside GenerationTaskProvider.");
  }
  return context;
}

