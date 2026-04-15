// What this file does: Auth context — stores login state across all pages.
import { createContext, useContext, useState, useCallback } from 'react'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const token = localStorage.getItem('cmia_token')
    const username = localStorage.getItem('cmia_user')
    return token ? { username, token } : null
  })
  const [backend, setBackend] = useState('azure')

  const login = useCallback((username, token) => {
    localStorage.setItem('cmia_token', token)
    localStorage.setItem('cmia_user', username)
    setUser({ username, token })
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('cmia_token')
    localStorage.removeItem('cmia_user')
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, login, logout, backend, setBackend }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
