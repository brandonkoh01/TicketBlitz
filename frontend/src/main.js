import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import UiButton from './components/ui/UiButton.vue'
import SectionLabel from './components/ui/SectionLabel.vue'
import FeatureCard from './components/ui/FeatureCard.vue'
import StatCard from './components/ui/StatCard.vue'
import MetricCard from './components/ui/MetricCard.vue'
import EventCard from './components/ui/EventCard.vue'
import FooterLinkGroup from './components/ui/FooterLinkGroup.vue'
import UiMaterialIcon from './components/ui/UiMaterialIcon.vue'
import UiDashboardPanel from './components/ui/UiDashboardPanel.vue'
import UiToggleSwitch from './components/ui/UiToggleSwitch.vue'
import './style.css'

const app = createApp(App)

app.component('UiButton', UiButton)
app.component('SectionLabel', SectionLabel)
app.component('FeatureCard', FeatureCard)
app.component('StatCard', StatCard)
app.component('MetricCard', MetricCard)
app.component('EventCard', EventCard)
app.component('FooterLinkGroup', FooterLinkGroup)
app.component('UiMaterialIcon', UiMaterialIcon)
app.component('UiDashboardPanel', UiDashboardPanel)
app.component('UiToggleSwitch', UiToggleSwitch)

app.use(router)

app.mount('#app')
