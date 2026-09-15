// JSON is data, never evaluated as JavaScript or AppleScript source.
function run(argv) {
    const data = JSON.parse(argv[0]);
    const app = Application.currentApplication();
    app.includeStandardAdditions = true;
    const options = data.options;
    try {
        if (options.length <= 3 && options.every(x => x.length < 28 && x.indexOf("\n") < 0)) {
            const reply = app.displayDialog(data.message, {
                withTitle: data.title, buttons: options, defaultButton: options[0]
            });
            return JSON.stringify({choice: reply.buttonReturned});
        }
        const reply = app.chooseFromList(options, {
            withTitle: data.title, withPrompt: data.message,
            okButtonName: "Continue", cancelButtonName: "Cancel",
            multipleSelectionsAllowed: false, emptySelectionAllowed: false
        });
        return JSON.stringify({choice: reply ? reply[0] : null});
    } catch (e) {
        if (e.errorNumber === -128) return JSON.stringify({choice: null});
        throw e;
    }
}
