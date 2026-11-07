import { BadRequestException, type PipeTransform } from '@nestjs/common';
import type { z } from 'zod';

/** Validates a body / param / query against a zod schema; the handler receives the parsed output. */
export class ZodPipe<T extends z.ZodType> implements PipeTransform<unknown, z.output<T>> {

    constructor(private readonly schema: T) {}

    public transform(value: unknown): z.output<T> {
        const result = this.schema.safeParse(value);

        if (!result.success)
            throw new BadRequestException({
                message: 'Invalid request',
                issues:  result.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message })),
            });

        return result.data;
    }
}
