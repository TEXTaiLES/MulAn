import { Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { UnsavedProvider } from './context/UnsavedContext'
import { AnnotatorPage } from './pages/AnnotatorPage'
import { ConvertPage } from './pages/ConvertPage'
import { ConvertResultPage } from './pages/ConvertResultPage'
import { HomePage } from './pages/HomePage'
import { ViewerPage } from './pages/ViewerPage'

export function App() {
  return <UnsavedProvider><Routes><Route element={<Shell />}><Route index element={<HomePage />} /><Route path="convert" element={<ConvertPage />} /><Route path="convert/result/:imageId" element={<ConvertResultPage />} /><Route path="viewer" element={<ViewerPage />} /><Route path="annotator" element={<AnnotatorPage />} /><Route path="*" element={<HomePage />} /></Route></Routes></UnsavedProvider>
}

