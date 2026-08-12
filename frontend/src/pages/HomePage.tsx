import { Images, Layers3, WandSparkles } from 'lucide-react'
import { Link } from 'react-router-dom'

const features = [
  { to: '/convert', icon: WandSparkles, title: 'BMP → TIFF', text: 'Convert ordered grayscale and RGB BMP inputs to a multiband TIFF.' },
  { to: '/viewer', icon: Images, title: 'Multispectral Viewer', text: 'View TIFF channels individually or in a grid.' },
  { to: '/annotator', icon: Layers3, title: 'Multispectral Annotator', text: 'Create pixel-aligned semantic segmentation masks.' },
]
export function HomePage() { return <div className="home page"><section className="hero"><span className="eyebrow">Multispectral image analysis</span><h1>MulAn: Multispectral Image Viewer and Annotator</h1><p>Convert BMP imagery to multiband TIFF, inspect spectral channels, and create semantic masks.</p></section><section className="feature-grid">{features.map(item => <Link className="feature-card" to={item.to} key={item.to}><span className="feature-icon"><item.icon /></span><h2>{item.title}</h2><p>{item.text}</p><span className="card-link">Open →</span></Link>)}</section></div> }
