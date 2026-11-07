import { container, singleton } from 'tsyringe'

// From Quarry's SDKManager (after PretzelGraph's). Needs `import 'reflect-metadata'` before anything (main.tsx).

// An SDK's class: constructed by the container, with no injected arguments.
type SDKClass = new () => object

interface Cleanable {
    cleanup?: () => void
}

// SDK name → its class; first registration wins, so a hot reload keeps the original.
const registry = new Map<string, SDKClass>()

// Resolved instances by name, so they (and their state) survive a hot reload.
const instances = new Map<string, object>()

/**
 * SDKs as named singletons in a tsyringe container.
 *
 *   @SDK('Trigger')
 *   export class TriggerSDKImpl extends BaseSDK<State> { … }
 *
 *   export const TriggerSDK = SDK.get<TriggerSDKImpl>('Trigger')
 *
 * `SDK.get` resolves when it's called, not when a module loads — so one SDK can reach another
 * (`SDK.get<OtherSDKImpl>('Other')` with a type-only import) without the two modules importing each other.
 */
function createSDKDecorator(name: string) {
    return function <T extends SDKClass>(target: T): T {
        singleton()(target)

        if (!registry.has(name))
            registry.set(name, target)

        return target
    }
}

createSDKDecorator.get = function <T>(name: string): T {
    const resolved = instances.get(name)

    if (resolved)
        return resolved as T

    const SDKClass = registry.get(name)

    if (!SDKClass)
        throw new Error(`[SDK] "${name}" is not registered. Is its module imported?`)

    const instance = container.resolve(SDKClass)

    instances.set(name, instance)

    return instance as T
}

/** Calls `cleanup()` on every resolved SDK. */
createSDKDecorator.cleanup = function (): void {
    for (const instance of instances.values())
        (instance as Cleanable).cleanup?.()
}

export const SDK = createSDKDecorator
