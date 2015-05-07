// The boltdb package implements a storage engine that interfaces with BoltDB.
package boltdb

import (
	"errors"

	"github.com/boltdb/bolt"
	"github.com/chop-dbhi/origins/engine"
)

var (
	ErrPathRequired = errors.New("Path to the boltdb file required")
)

type Tx struct {
	tx *bolt.Tx
}

func (t *Tx) Get(p, k string) ([]byte, error) {
	b := t.tx.Bucket([]byte(p))

	// No bucket.
	if b == nil {
		return nil, nil
	}

	v := b.Get([]byte(k))

	if v == nil {
		return nil, nil
	}

	// Copy bytes.
	c := make([]byte, len(v))
	copy(c, v)

	return c, nil
}

func (t *Tx) Set(p, k string, v []byte) error {
	b, err := t.tx.CreateBucketIfNotExists([]byte(p))

	if err != nil {
		return err
	}

	return b.Put([]byte(k), v)
}

func (t *Tx) Incr(p, k string) (uint64, error) {
	b, err := t.tx.CreateBucketIfNotExists([]byte(p))

	if err != nil {
		return 0, err
	}

	key := []byte(k)

	buf := b.Get(key)

	var id uint64

	if buf != nil {
		id = engine.DecodeCounter(buf)
	}

	id++

	if err = b.Put(key, engine.EncodeCounter(id)); err != nil {
		return 0, err
	}

	return id, err
}

type Engine struct {
	Path string
}

func (e *Engine) Get(p, k string) ([]byte, error) {
	db, err := bolt.Open(e.Path, 0600, nil)

	if err != nil {
		return nil, err
	}

	defer db.Close()

	var v []byte

	err = db.View(func(tx *bolt.Tx) error {
		t := &Tx{tx}

		v, err = t.Get(p, k)

		return err
	})

	if err != nil {
		return nil, err
	}

	return v, nil
}

func (e *Engine) Set(p, k string, v []byte) error {
	db, err := bolt.Open(e.Path, 0600, nil)

	if err != nil {
		return err
	}

	defer db.Close()

	return db.Update(func(tx *bolt.Tx) error {
		t := &Tx{tx}

		return t.Set(p, k, v)
	})
}

func (e *Engine) Incr(p, k string) (uint64, error) {
	db, err := bolt.Open(e.Path, 0600, nil)

	if err != nil {
		return 0, err
	}

	defer db.Close()

	var id uint64

	err = db.Update(func(tx *bolt.Tx) error {
		t := &Tx{tx}

		id, err = t.Incr(p, k)

		return err
	})

	if err != nil {
		return 0, err
	}

	return id, nil
}

func (e *Engine) Multi(f func(tx engine.Tx) error) error {
	db, err := bolt.Open(e.Path, 0600, nil)

	if err != nil {
		return err
	}

	defer db.Close()

	return db.Update(func(tx *bolt.Tx) error {
		return f(&Tx{tx})
	})
}

func Init(opts engine.Options) (*Engine, error) {
	path := opts.GetString("path")

	if path == "" {
		return nil, ErrPathRequired
	}

	e := Engine{
		Path: path,
	}

	return &e, nil
}
