import type { Log } from './log'

// Action groups as classes (Quarry's). An action that can fail handles it itself — logs it, toasts it, rethrows
// so the caller can still react:
//
//     async create(trigger) {
//         try { … }
//         catch (error) {
//             this.log.error('create failed', describeError(error))
//             NotificationSDK.toast.error("Couldn't save the trigger", errorMessage(error))
//             throw error
//         }
//     }

/**
 * An SDK's group of actions (`actions.trigger`, `actions.hit`, …). Binds every method to its instance, so an action
 * can be passed as a callback. Each group names its log once: `protected readonly log = log.withContext('Trigger.Actions')`.
 */
export abstract class ActionGroup<SDK> {

    protected abstract readonly log: Log

    constructor(protected readonly sdk: SDK) {
        let prototype: object | null = Object.getPrototypeOf(this)

        while (prototype && prototype !== ActionGroup.prototype) {
            for (const name of Object.getOwnPropertyNames(prototype)) {
                const descriptor = Object.getOwnPropertyDescriptor(prototype, name)

                if (name !== 'constructor' && typeof descriptor?.value === 'function')
                    Object.defineProperty(this, name, { value: descriptor.value.bind(this) })
            }

            prototype = Object.getPrototypeOf(prototype)
        }
    }
}
