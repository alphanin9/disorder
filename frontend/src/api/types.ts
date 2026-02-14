export interface paths {
    "/challenges": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Challenges */
        get: operations["list_challenges_challenges_get"];
        put?: never;
        /** Create Challenge Route */
        post: operations["create_challenge_route_challenges_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/challenges/{challenge_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Challenge */
        get: operations["get_challenge_challenges__challenge_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Challenge Route */
        patch: operations["update_challenge_route_challenges__challenge_id__patch"];
        trace?: never;
    };
    "/ctfs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Ctfs Route */
        get: operations["list_ctfs_route_ctfs_get"];
        put?: never;
        /** Create Ctf Route */
        post: operations["create_ctf_route_ctfs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ctfs/{ctf_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Ctf Route */
        get: operations["get_ctf_route_ctfs__ctf_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Ctf Route */
        patch: operations["update_ctf_route_ctfs__ctf_id__patch"];
        trace?: never;
    };
    "/healthz": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Healthcheck */
        get: operations["healthcheck_healthz_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/integrations/ctfd/config": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Ctfd */
        get: operations["get_ctfd_integrations_ctfd_config_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/integrations/ctfd/sync": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Sync Ctfd */
        post: operations["sync_ctfd_integrations_ctfd_sync_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Run */
        post: operations["start_run_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Run */
        get: operations["get_run_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/runs/{run_id}/logs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Run Logs */
        get: operations["get_run_logs_runs__run_id__logs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/runs/{run_id}/result": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Run Result Payload */
        get: operations["get_run_result_payload_runs__run_id__result_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** ChallengeCreateRequest */
        ChallengeCreateRequest: {
            /** Artifacts */
            artifacts?: {
                [key: string]: unknown;
            }[];
            /**
             * Category
             * @default misc
             */
            category: string;
            /**
             * Ctf Id
             * Format: uuid
             */
            ctf_id: string;
            /**
             * Description Md
             * @default
             */
            description_md: string;
            /** Description Raw */
            description_raw?: string | null;
            /** Flag Regex */
            flag_regex?: string | null;
            /** Local Deploy Hints */
            local_deploy_hints?: {
                [key: string]: unknown;
            };
            /** Name */
            name: string;
            /**
             * Platform
             * @default manual
             */
            platform: string;
            /** Platform Challenge Id */
            platform_challenge_id?: string | null;
            /**
             * Points
             * @default 0
             */
            points: number;
            /** Remote Endpoints */
            remote_endpoints?: {
                [key: string]: unknown;
            }[];
        };
        /** ChallengeListResponse */
        ChallengeListResponse: {
            /** Items */
            items: components["schemas"]["ChallengeManifestRead"][];
        };
        /** ChallengeManifestRead */
        ChallengeManifestRead: {
            /** Artifacts */
            artifacts: {
                [key: string]: unknown;
            }[];
            /** Category */
            category: string;
            /**
             * Ctf Id
             * Format: uuid
             */
            ctf_id: string;
            /** Ctf Name */
            ctf_name?: string | null;
            /** Description Md */
            description_md: string;
            /** Description Raw */
            description_raw?: string | null;
            /** Flag Regex */
            flag_regex?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Local Deploy Hints */
            local_deploy_hints: {
                [key: string]: unknown;
            };
            /** Name */
            name: string;
            /** Platform */
            platform: string;
            /** Platform Challenge Id */
            platform_challenge_id: string;
            /** Points */
            points: number;
            /** Remote Endpoints */
            remote_endpoints: {
                [key: string]: unknown;
            }[];
            /**
             * Synced At
             * Format: date-time
             */
            synced_at: string;
        };
        /** ChallengeUpdateRequest */
        ChallengeUpdateRequest: {
            /** Artifacts */
            artifacts?: {
                [key: string]: unknown;
            }[] | null;
            /** Category */
            category?: string | null;
            /** Ctf Id */
            ctf_id?: string | null;
            /** Description Md */
            description_md?: string | null;
            /** Description Raw */
            description_raw?: string | null;
            /** Flag Regex */
            flag_regex?: string | null;
            /** Local Deploy Hints */
            local_deploy_hints?: {
                [key: string]: unknown;
            } | null;
            /** Name */
            name?: string | null;
            /** Points */
            points?: number | null;
            /** Remote Endpoints */
            remote_endpoints?: {
                [key: string]: unknown;
            }[] | null;
        };
        /** CTFCreateRequest */
        CTFCreateRequest: {
            /**
             * Default Flag Regex
             * @default flag\{.*?\}
             */
            default_flag_regex: string | null;
            /** Name */
            name: string;
            /** Notes */
            notes?: string | null;
            /** Platform */
            platform?: string | null;
            /** Slug */
            slug: string;
        };
        /** CTFdConfigResponse */
        CTFdConfigResponse: {
            /** Base Url */
            base_url: string;
            /** Configured */
            configured: boolean;
        };
        /** CTFdSyncRequest */
        CTFdSyncRequest: {
            /** Api Token */
            api_token?: string | null;
            /** Base Url */
            base_url?: string | null;
        };
        /** CTFListResponse */
        CTFListResponse: {
            /** Items */
            items: components["schemas"]["CTFRead"][];
        };
        /** CTFRead */
        CTFRead: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Default Flag Regex */
            default_flag_regex?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Notes */
            notes?: string | null;
            /** Platform */
            platform?: string | null;
            /** Slug */
            slug: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** CTFUpdateRequest */
        CTFUpdateRequest: {
            /** Default Flag Regex */
            default_flag_regex?: string | null;
            /** Name */
            name?: string | null;
            /** Notes */
            notes?: string | null;
            /** Platform */
            platform?: string | null;
            /** Slug */
            slug?: string | null;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** RunCreateRequest */
        RunCreateRequest: {
            /**
             * Backend
             * @default mock
             */
            backend: string;
            /**
             * Challenge Id
             * Format: uuid
             */
            challenge_id: string;
            /**
             * Local Deploy Enabled
             * @default false
             */
            local_deploy_enabled: boolean;
            /** Stop Criteria */
            stop_criteria?: {
                [key: string]: unknown;
            } | null;
        };
        /** RunLogsResponse */
        RunLogsResponse: {
            /** Eof */
            eof: boolean;
            /** Logs */
            logs: string;
            /** Next Offset */
            next_offset: number;
            /** Offset */
            offset: number;
            /**
             * Run Id
             * Format: uuid
             */
            run_id: string;
        };
        /** RunRead */
        RunRead: {
            /** Allowed Endpoints */
            allowed_endpoints: {
                [key: string]: unknown;
            }[];
            /** Backend */
            backend: string;
            /** Budgets */
            budgets: {
                [key: string]: unknown;
            };
            /**
             * Challenge Id
             * Format: uuid
             */
            challenge_id: string;
            /** Error Message */
            error_message?: string | null;
            /** Finished At */
            finished_at?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Local Deploy */
            local_deploy: {
                [key: string]: unknown;
            };
            /** Paths */
            paths: {
                [key: string]: unknown;
            };
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /** Status */
            status: string;
            /** Stop Criteria */
            stop_criteria: {
                [key: string]: unknown;
            };
        };
        /** RunResultRead */
        RunResultRead: {
            /**
             * Finished At
             * Format: date-time
             */
            finished_at: string;
            /** Logs Object Key */
            logs_object_key: string;
            /** Result Json Object Key */
            result_json_object_key: string;
            /**
             * Run Id
             * Format: uuid
             */
            run_id: string;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /** Status */
            status: string;
        };
        /** RunStatusResponse */
        RunStatusResponse: {
            result?: components["schemas"]["RunResultRead"] | null;
            run: components["schemas"]["RunRead"];
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    list_challenges_challenges_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChallengeListResponse"];
                };
            };
        };
    };
    create_challenge_route_challenges_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChallengeCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChallengeManifestRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_challenge_challenges__challenge_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                challenge_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChallengeManifestRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_challenge_route_challenges__challenge_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                challenge_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChallengeUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChallengeManifestRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_ctfs_route_ctfs_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CTFListResponse"];
                };
            };
        };
    };
    create_ctf_route_ctfs_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CTFCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CTFRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_ctf_route_ctfs__ctf_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                ctf_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CTFRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_ctf_route_ctfs__ctf_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                ctf_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CTFUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CTFRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    healthcheck_healthz_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
    get_ctfd_integrations_ctfd_config_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CTFdConfigResponse"];
                };
            };
        };
    };
    sync_ctfd_integrations_ctfd_sync_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CTFdSyncRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    start_run_runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RunCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_run_runs__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunStatusResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_run_logs_runs__run_id__logs_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunLogsResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_run_result_payload_runs__run_id__result_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
