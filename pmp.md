Context: Jira DATAUSER-6454. For Azure data sources, only an Admin or a Data Content Manager (DCM) of the dataset's own BU/SU may see and use these three actions:
- "Deploy data source"
- "Deploy feeder access"
- "Request workspace"
Non-Azure behaviour must stay exactly as it was before this branch.

The backend now returns a boolean `azureDeployable` on the dataset detail response. It is true when the user is Admin or a DCM of the dataset's BU/SU. The frontend must use this flag. It must not compute BU/SU membership itself.

Make exactly these changes and nothing else. No new comments, no refactoring, no formatting changes to untouched lines.

1. src/sdc-dataset/contexts/user.context.tsx
   Remove everything this branch added for `dataContentManagerBuSuIds` and `setDataContentManagerBuSuIds`: the interface fields, the context defaults, the useState, and the provider value entries. The file should match the develop branch.

2. src/sdc-dataset/pages/Dataset/DatasetPage.tsx
   Remove `setDataContentManagerBuSuIds` from the UserContext destructuring. Delete the `setDataContentManagerBuSuIds(...)` call inside `fetchAndSetUserRoles`, including the `??` fallback chain. Leave `setIsAdmin` and `setIsDataContentManager` as they are.

3. src/services/datasets.service.types.ts
   In the dataset interface, add `azureDeployable: boolean;` directly below `editable: boolean;`.

4. src/sdc-dataset/components/Dataset/data-source/card/DataSourceCard.tsx
   - Delete the `isDataContentManagerForDataset` constant.
   - Set `hasDataSourceDeployPermission` back to: `isAdmin || isDataContentManager || isManager || isInBackupManager`.
   - Keep `isAzureDataSource` as it is: `dataSourceType === 'DATA_LAKE' && hostingPlatform === DataSourceHostingPlatform.AZURE`.
   - Change `canShowDeployAction` to: `isAzureDataSource ? !!dataset?.azureDeployable : hasDataSourceDeployPermission`.
   - Every JSX condition that shows the deploy data source or deploy feeder action must use `canShowDeployAction`, not `hasDataSourceDeployPermission`. List each place you changed.
   - Remove any variables or imports that become unused.

5. DataSourceDeployConfirmationDialog.tsx and DataSourceDeployPermissionDialog.tsx
   Do not change them. Their `.catch` already shows the `accessDenied` message on HTTP 403.

6. src/sdc-dataset/components/Dataset/locales/en.json
   Next to the other `dataset.dataSource.card.actions.dialog.deployConfirmation.*` keys, add:
   "dataset.dataSource.card.actions.dialog.deploy.accessDenied": "Access Denied: You are not authorized as the Data Content Manager for this BU/SU."
   Keep the JSON valid.

7. src/sdc-dataset/components/Dataset/data-lake-workspace/FeederAccessCard.tsx
   - Import `FeederAccessHostingPlatform` from the existing `feederAccess.service.types` import.
   - Find the button render condition `{showRequestWorkspaceButton && (`. Change it so the button renders only when `showRequestWorkspaceButton` is true AND (`feederAccess?.hostingPlatform !== FeederAccessHostingPlatform.AZURE` OR `dataset?.azureDeployable`).
   - Do not change the other `dataset?.editable` conditions in this file.

8. src/sdc-dataset/components/Dataset/data-lake-workspace/request-workspace-information/confirmation/RequestWorkspaceConfirmationDialog.tsx
   - Import `DXError` from `common/errors`, using the correct relative path as in the sibling dialog files.
   - In `requestWorkspaceCreation`, the `FeederAccessService.requestWorkspaceCreation(...)` promise has `.then` and `.finally` but no `.catch`. Add a `.catch((error: DXError) => ...)` between them. It must call `toastifyErrorMessage` with `intl.formatMessage({ id: 'dataset.dataSource.card.actions.dialog.deploy.accessDenied' })` when `error.response?.status === 403`, and with `error.message` otherwise. Follow the same pattern used in DataSourceDeployConfirmationDialog.tsx.

After editing:
- Run the TypeScript check and lint (`yarn tsc --noEmit` and the repo's lint script). Fix only errors caused by these changes.
- Run the existing tests for the files you touched. If a test mocks a dataset object and fails because `azureDeployable` is missing, add `azureDeployable: true` to that mock.
- Show me the final diff for every file.
