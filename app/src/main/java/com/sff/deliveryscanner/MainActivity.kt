package com.sff.deliveryscanner

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.provider.MediaStore
import android.os.Environment
import androidx.core.content.FileProvider
import java.io.File
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient

class MainActivity : Activity() {
    private var uploadCallback: ValueCallback<Array<Uri>>? = null
    private var cameraUri: Uri? = null
    private val FILE_REQUEST = 1001
    private val CAMERA_REQUEST = 1002

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (android.os.Build.VERSION.SDK_INT >= 23 && checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.CAMERA), 2001)
        }

        val web = WebView(this)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.settings.allowFileAccess = true
        web.settings.allowContentAccess = true
        web.settings.mediaPlaybackRequiresUserGesture = false
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                return handleExternal(request.url.toString())
            }
            @Suppress("DEPRECATION")
            override fun shouldOverrideUrlLoading(view: WebView, url: String): Boolean = handleExternal(url)
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(view: WebView?, filePathCallback: ValueCallback<Array<Uri>>?, params: FileChooserParams?): Boolean {
                uploadCallback?.onReceiveValue(null)
                uploadCallback = filePathCallback
                showCameraOrGallery()
                return true
            }
        }
        web.loadUrl("file:///android_asset/index.html")
        setContentView(web)
    }

    private fun handleExternal(url: String): Boolean {
        if (url.startsWith("https://wa.me/") || url.startsWith("https://api.whatsapp.com/") || url.startsWith("whatsapp://")) {
            try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) } catch (_: Exception) {}
            return true
        }
        return false
    }

    private fun showCameraOrGallery() {
        val options = arrayOf("📷 Camera", "🖼️ Gallery", "Cancel")
        AlertDialog.Builder(this)
            .setTitle("Choose Order Photo")
            .setItems(options) { _, which ->
                when (which) {
                    0 -> {
                        if (android.os.Build.VERSION.SDK_INT >= 23 &&
                            checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                            requestPermissions(arrayOf(Manifest.permission.CAMERA), 2001)
                        } else {
                            openCamera()
                        }
                    }
                    1 -> openGallery()
                    else -> {
                        uploadCallback?.onReceiveValue(null)
                        uploadCallback = null
                    }
                }
            }
            .setOnCancelListener {
                uploadCallback?.onReceiveValue(null)
                uploadCallback = null
            }
            .show()
    }

    private fun openGallery() {
        val gallery = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "image/*"
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, false)
        }
        startActivityForResult(gallery, FILE_REQUEST)
    }

    private fun openCamera() {
        val camera = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
        if (camera.resolveActivity(packageManager) == null) {
            android.widget.Toast.makeText(this, "Camera app not available", android.widget.Toast.LENGTH_SHORT).show()
            return
        }
        try {
            val dir = File(cacheDir, "camera").apply { mkdirs() }
            val file = File.createTempFile("delivery_", ".jpg", dir)
            cameraUri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
            camera.putExtra(MediaStore.EXTRA_OUTPUT, cameraUri)
            camera.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_READ_URI_PERMISSION)
            camera.clipData = android.content.ClipData.newRawUri("DeliveryPhoto", cameraUri)
            startActivityForResult(camera, CAMERA_REQUEST)
        } catch (e: Exception) {
            cameraUri = null
            android.widget.Toast.makeText(this, "Cannot open camera: ${e.message}", android.widget.Toast.LENGTH_LONG).show()
            uploadCallback?.onReceiveValue(null)
            uploadCallback = null
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 2001) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                openCamera()
            } else {
                android.widget.Toast.makeText(this, "Camera permission is required to take a photo", android.widget.Toast.LENGTH_LONG).show()
            }
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == FILE_REQUEST || requestCode == CAMERA_REQUEST) {
            val result = if (resultCode == RESULT_OK) {
                val uri = if (requestCode == CAMERA_REQUEST) cameraUri else data?.data
                if (uri != null) arrayOf(uri) else null
            } else null
            uploadCallback?.onReceiveValue(result)
            uploadCallback = null
            cameraUri = null
        }
    }

}
