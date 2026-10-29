import { audioScenario } from './audio_scenario.mjs'
import { pwaScenario } from './pwa_scenario.mjs'

export async function platformScenario(context) {
  const state = await audioScenario(context)
  if (context.pwaTest) await pwaScenario({ ...context, ...state })
}
