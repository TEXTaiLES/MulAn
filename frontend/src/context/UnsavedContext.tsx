import { createContext, useContext, useState, type ReactNode } from 'react'

const Context = createContext({ dirty: false, setDirty: (_value: boolean) => {} })
export function UnsavedProvider({ children }: { children: ReactNode }) {
  const [dirty, setDirty] = useState(false)
  return <Context.Provider value={{ dirty, setDirty }}>{children}</Context.Provider>
}
export const useUnsaved = () => useContext(Context)

