import { Intent, OverlayToaster, type Toaster } from '@blueprintjs/core'
import { SDK } from '../SDKManager'

const TOAST_TIMEOUT_MS = 6_000

/** Toasts (Blueprint's OverlayToaster), for actions to report what they did or why they failed. */
@SDK('Notification')
export class NotificationSDKImpl {

    private toaster: Promise<Toaster> | null = null

    public readonly toast = {
        success: (message: string, description?: string) => this.show(Intent.SUCCESS, message, description),
        warning: (message: string, description?: string) => this.show(Intent.WARNING, message, description),
        error:   (message: string, description?: string) => this.show(Intent.DANGER, message, description),
    }

    private async show(intent: Intent, message: string, description: string | undefined): Promise<void> {
        this.toaster ??= OverlayToaster.create({ position: 'top-right' })

        const toaster = await this.toaster
        let text = message

        if (description)
            text = `${message}: ${description}`

        toaster.show({
            intent,
            message: text,
            timeout: TOAST_TIMEOUT_MS,
        })
    }

    public cleanup(): void {}
}

export const NotificationSDK = SDK.get<NotificationSDKImpl>('Notification')
