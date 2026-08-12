import { Images, Layers3, WandSparkles } from 'lucide-react'
import { Link } from 'react-router-dom'

const features = [
  { to: '/convert', icon: WandSparkles, title: 'BMP → TIFF', text: 'Combine ordered grayscale and RGB BMP channels into one multispectral TIFF.' },
  { to: '/viewer', icon: Images, title: 'Multispectral Viewer', text: 'Inspect every spectral channel alone or in a responsive grid.' },
  { to: '/annotator', icon: Layers3, title: 'Multispectral Annotator', text: 'Paint ML-ready semantic class masks aligned to the source raster.' },
]
export function HomePage() { return <div className="home page"><section className="hero"><span className="eyebrow">Multispectral imagery, made workable</span><h1>Convert. Inspect. Annotate.</h1><p>MulAn keeps every spectral band and semantic class exactly where it belongs.</p></section><section className="feature-grid">{features.map(item => <Link className="feature-card" to={item.to} key={item.to}><span className="feature-icon"><item.icon /></span><h2>{item.title}</h2><p>{item.text}</p><span className="card-link">Open tool →</span></Link>)}</section></div> }
