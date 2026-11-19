const { packager } = require('@electron/packager');
const path = require('node:path');

async function build() {
    for (const name of ['OGKParent', 'OGKChild']) {
        const [output] = await packager({
            dir: __dirname,
            name,
            platform: 'win32',
            arch: 'x64',
            out: path.join(__dirname, '..', 'dist', 'desktop'),
            asar: true,
            overwrite: true,
            ignore: /(^|\/)(build-windows\.cjs|package-lock\.json)$/,
        });
        console.log(output);
    }
}

build().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
